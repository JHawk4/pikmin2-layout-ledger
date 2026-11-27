// The pinned CaveGen3 rev (from Cargo.toml), written into the vectors.
fn main() {
    let toml = std::fs::read_to_string("Cargo.toml").unwrap();
    let rev = toml.split("rev = \"").nth(1).and_then(|s| s.split('"').next()).unwrap_or("unknown");
    println!("cargo:rustc-env=CAVEGEN3_REV={rev}");
    println!("cargo:rerun-if-changed=Cargo.toml");
}
