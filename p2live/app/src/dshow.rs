//! Cameras through DirectShow. The OBS Virtual Camera is a DirectShow filter: apps that read
//! cameras through Media Foundation (the Windows Camera app, and so Rust's usual camera crates)
//! often do not see it, while DirectShow apps (OBS itself, Zoom, Discord, OpenCV) do.
//!
//! The graph is camera -> Sample Grabber (asking for RGB24, so DirectShow inserts whatever
//! decoder the camera needs) -> Null Renderer, with a callback that receives every frame.

use std::ffi::c_void;
use std::sync::mpsc::SyncSender;
use std::sync::Mutex;

use windows::core::{implement, interface, IUnknown, IUnknown_Vtbl, Interface, BOOL, BSTR, GUID, HRESULT, PCWSTR};
use windows::Win32::Foundation::S_OK;
use windows::Win32::Media::DirectShow::{IAMStreamConfig, IBaseFilter, ICaptureGraphBuilder2, ICreateDevEnum, IGraphBuilder, IMediaControl};
use windows::Win32::Media::MediaFoundation::{
    AM_MEDIA_TYPE, CLSID_CaptureGraphBuilder2, CLSID_FilterGraph, CLSID_SystemDeviceEnum, CLSID_VideoInputDeviceCategory, FORMAT_VideoInfo,
    MEDIASUBTYPE_RGB24, MEDIATYPE_Video, PIN_CATEGORY_CAPTURE, VIDEOINFOHEADER,
};
use windows::Win32::System::Com::StructuredStorage::IPropertyBag;
use windows::Win32::System::Com::{CoCreateInstance, CoInitializeEx, CoTaskMemFree, IEnumMoniker, IMoniker, CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED};
use windows::Win32::System::Variant::VARIANT;

use crate::capture::Frame;

const CLSID_SAMPLE_GRABBER: GUID = GUID::from_u128(0xc1f400a0_3f08_11d3_9f0b_006008039e37);
const CLSID_NULL_RENDERER: GUID = GUID::from_u128(0xc1f400a4_3f08_11d3_9f0b_006008039e37);

// qedit.h, which the windows crate's metadata leaves out
#[interface("0579154A-2B53-4994-B0D0-E773148EFF85")]
unsafe trait ISampleGrabberCB: IUnknown {
    fn SampleCB(&self, time: f64, sample: *mut c_void) -> HRESULT;
    fn BufferCB(&self, time: f64, buf: *mut u8, len: i32) -> HRESULT;
}

#[interface("6B652FFF-11FE-4fce-92AD-0266B5D7C78F")]
unsafe trait ISampleGrabber: IUnknown {
    fn SetOneShot(&self, one_shot: BOOL) -> HRESULT;
    fn SetMediaType(&self, mt: *const AM_MEDIA_TYPE) -> HRESULT;
    fn GetConnectedMediaType(&self, mt: *mut AM_MEDIA_TYPE) -> HRESULT;
    fn SetBufferSamples(&self, buffer: BOOL) -> HRESULT;
    fn GetCurrentBuffer(&self, size: *mut i32, buf: *mut i32) -> HRESULT;
    fn GetCurrentSample(&self, sample: *mut *mut c_void) -> HRESULT;
    fn SetCallback(&self, cb: *mut c_void, which: i32) -> HRESULT;
}

fn com() {
    // a thread may already be in a COM apartment (the GUI thread); either way is fine here
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
    }
}

fn devices() -> windows::core::Result<Vec<IMoniker>> {
    com();
    unsafe {
        let de: ICreateDevEnum = CoCreateInstance(&CLSID_SystemDeviceEnum, None, CLSCTX_INPROC_SERVER)?;
        let mut en: Option<IEnumMoniker> = None;
        de.CreateClassEnumerator(&CLSID_VideoInputDeviceCategory, &mut en, 0)?;
        let mut out = Vec::new();
        let Some(en) = en else { return Ok(out) }; // S_FALSE: no cameras
        loop {
            let mut m = [None];
            let mut got = 0u32;
            if en.Next(&mut m, Some(&mut got)) != S_OK || got == 0 {
                break;
            }
            if let Some(m) = m[0].take() {
                out.push(m);
            }
        }
        Ok(out)
    }
}

fn friendly_name(m: &IMoniker) -> String {
    unsafe {
        let Ok(bag) = m.BindToStorage::<_, _, IPropertyBag>(None, None) else { return "?".into() };
        let mut v = VARIANT::default();
        if bag.Read(windows::core::w!("FriendlyName"), &mut v, None).is_err() {
            return "?".into();
        }
        BSTR::try_from(&v).map(|b| b.to_string()).unwrap_or_else(|_| "?".into())
    }
}

/// The names of the cameras DirectShow lists, in its order.
pub fn list() -> Vec<String> {
    devices().map(|d| d.iter().map(friendly_name).collect()).unwrap_or_default()
}

unsafe fn free_mt(mt: *mut AM_MEDIA_TYPE) {
    unsafe {
        let m = &mut *mt;
        if m.cbFormat != 0 && !m.pbFormat.is_null() {
            CoTaskMemFree(Some(m.pbFormat as *const c_void));
        }
        m.pbFormat = std::ptr::null_mut();
        m.cbFormat = 0;
        if let Some(u) = m.pUnk.take() {
            drop(u);
        }
    }
}

/// The camera's format closest to `want_lines` tall at 30 fps or more; set before connecting.
fn choose_format(cfg: &IAMStreamConfig, want_lines: i32) {
    unsafe {
        let (mut n, mut size) = (0i32, 0i32);
        if cfg.GetNumberOfCapabilities(&mut n, &mut size).is_err() {
            return;
        }
        let mut caps = vec![0u8; size.max(0) as usize + 64];
        let mut best: Option<(i64, *mut AM_MEDIA_TYPE)> = None;
        for i in 0..n {
            let mut mt: *mut AM_MEDIA_TYPE = std::ptr::null_mut();
            if cfg.GetStreamCaps(i, &mut mt, caps.as_mut_ptr()).is_err() || mt.is_null() {
                continue;
            }
            let m = &*mt;
            let mut keep = false;
            if m.formattype == FORMAT_VideoInfo && m.cbFormat as usize >= std::mem::size_of::<VIDEOINFOHEADER>() {
                let vih = &*(m.pbFormat as *const VIDEOINFOHEADER);
                let h = vih.bmiHeader.biHeight.abs();
                let fps = if vih.AvgTimePerFrame > 0 { 1e7 / vih.AvgTimePerFrame as f64 } else { 30.0 };
                let score = if fps >= 29.0 { 0 } else { 1_000_000 } + (h - want_lines).abs() as i64;
                if best.as_ref().is_none_or(|(s, _)| score < *s) {
                    if let Some((_, old)) = best.take() {
                        free_mt(old);
                        CoTaskMemFree(Some(old as *const c_void));
                    }
                    best = Some((score, mt));
                    keep = true;
                }
            }
            if !keep {
                free_mt(mt);
                CoTaskMemFree(Some(mt as *const c_void));
            }
        }
        if let Some((_, mt)) = best {
            let _ = cfg.SetFormat(mt);
            free_mt(mt);
            CoTaskMemFree(Some(mt as *const c_void));
        }
    }
}

#[implement(ISampleGrabberCB)]
struct Callback {
    w: usize,
    h: usize,
    bottom_up: bool,
    tx: Mutex<SyncSender<Frame>>,
}

impl ISampleGrabberCB_Impl for Callback_Impl {
    unsafe fn SampleCB(&self, _time: f64, _sample: *mut c_void) -> HRESULT {
        S_OK
    }
    unsafe fn BufferCB(&self, _time: f64, buf: *mut u8, len: i32) -> HRESULT {
        let (w, h) = (self.w, self.h);
        let stride = (w * 3 + 3) & !3;
        if buf.is_null() || (len as usize) < stride * h {
            return S_OK;
        }
        let src = unsafe { std::slice::from_raw_parts(buf, stride * h) };
        let mut rgb = vec![0u8; w * h * 3];
        for y in 0..h {
            let sy = if self.bottom_up { h - 1 - y } else { y };
            let s = &src[sy * stride..sy * stride + w * 3];
            let d = &mut rgb[y * w * 3..(y + 1) * w * 3];
            // BGR -> RGB
            for x in 0..w {
                d[x * 3] = s[x * 3 + 2];
                d[x * 3 + 1] = s[x * 3 + 1];
                d[x * 3 + 2] = s[x * 3];
            }
        }
        // a full queue means the reader is behind: drop this frame (the detector copes)
        let _ = self.tx.lock().unwrap().try_send(Frame::from_rgb(w, h, rgb));
        S_OK
    }
}

fn e(what: &'static str) -> impl Fn(windows::core::Error) -> String {
    move |err| format!("{what}: {err}")
}

/// A running camera graph; frames go to the channel until it is dropped.
pub struct Camera {
    control: IMediaControl,
    _graph: IGraphBuilder,
    _cb: ISampleGrabberCB,
    pub w: usize,
    pub h: usize,
    pub fps: f64,
}

// COM objects of the multithreaded apartment may be used from any thread
unsafe impl Send for Camera {}

impl Camera {
    /// Open the camera named `name` (the first with that name), aiming for about `want_lines`.
    pub fn open(name: &str, want_lines: i32, tx: SyncSender<Frame>) -> Result<Camera, String> {
        let devs = devices().map_err(e("listing cameras"))?;
        let m = devs.iter().find(|m| friendly_name(m) == name).ok_or_else(|| format!("no camera named {name:?}"))?;
        unsafe {
            let src: IBaseFilter = m.BindToObject(None, None).map_err(e("opening the camera"))?;
            let graph: IGraphBuilder = CoCreateInstance(&CLSID_FilterGraph, None, CLSCTX_INPROC_SERVER).map_err(e("filter graph"))?;
            let builder: ICaptureGraphBuilder2 = CoCreateInstance(&CLSID_CaptureGraphBuilder2, None, CLSCTX_INPROC_SERVER).map_err(e("capture graph"))?;
            builder.SetFiltergraph(&graph).map_err(e("capture graph"))?;
            graph.AddFilter(&src, PCWSTR(windows::core::w!("camera").as_ptr())).map_err(e("adding the camera"))?;
            let mut p: *mut c_void = std::ptr::null_mut();
            if builder.FindInterface(Some(&PIN_CATEGORY_CAPTURE), Some(&MEDIATYPE_Video), &src, &IAMStreamConfig::IID, &mut p).is_ok() && !p.is_null() {
                let cfg = IAMStreamConfig::from_raw(p);
                choose_format(&cfg, want_lines);
            }

            let grab_f: IBaseFilter = CoCreateInstance(&CLSID_SAMPLE_GRABBER, None, CLSCTX_INPROC_SERVER).map_err(e("Sample Grabber (qedit.dll)"))?;
            let grab: ISampleGrabber = grab_f.cast().map_err(e("Sample Grabber"))?;
            let mut mt = AM_MEDIA_TYPE { majortype: MEDIATYPE_Video, subtype: MEDIASUBTYPE_RGB24, ..Default::default() };
            grab.SetMediaType(&mt).ok().map_err(e("Sample Grabber format"))?;
            graph.AddFilter(&grab_f, PCWSTR(windows::core::w!("grabber").as_ptr())).map_err(e("adding the grabber"))?;
            let null: IBaseFilter = CoCreateInstance(&CLSID_NULL_RENDERER, None, CLSCTX_INPROC_SERVER).map_err(e("Null Renderer"))?;
            graph.AddFilter(&null, PCWSTR(windows::core::w!("null").as_ptr())).map_err(e("adding the renderer"))?;
            builder
                .RenderStream(Some(&PIN_CATEGORY_CAPTURE), &MEDIATYPE_Video, &src, &grab_f, &null)
                .map_err(e("connecting the camera (is another program using it?)"))?;

            grab.GetConnectedMediaType(&mut mt).ok().map_err(e("reading the format"))?;
            if mt.formattype != FORMAT_VideoInfo || mt.pbFormat.is_null() {
                free_mt(&mut mt);
                return Err("the camera's format is not a plain video format".into());
            }
            let vih = &*(mt.pbFormat as *const VIDEOINFOHEADER);
            let w = vih.bmiHeader.biWidth.unsigned_abs() as usize;
            let h = vih.bmiHeader.biHeight.unsigned_abs() as usize;
            let bottom_up = vih.bmiHeader.biHeight > 0;
            let fps = if vih.AvgTimePerFrame > 0 { 1e7 / vih.AvgTimePerFrame as f64 } else { 30.0 };
            free_mt(&mut mt);

            let cb: ISampleGrabberCB = Callback { w, h, bottom_up, tx: Mutex::new(tx) }.into();
            grab.SetBufferSamples(BOOL(0)).ok().map_err(e("grabber"))?;
            grab.SetOneShot(BOOL(0)).ok().map_err(e("grabber"))?;
            grab.SetCallback(cb.as_raw(), 1).ok().map_err(e("grabber callback"))?;
            let control: IMediaControl = graph.cast().map_err(e("media control"))?;
            control.Run().map_err(e("starting the camera"))?;
            Ok(Camera { control, _graph: graph, _cb: cb, w, h, fps })
        }
    }
}

impl Drop for Camera {
    fn drop(&mut self) {
        unsafe {
            let _ = self.control.Stop();
        }
    }
}
