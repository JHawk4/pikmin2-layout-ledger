// Prints every treasure placed on a story sublevel for a seed: "name<TAB>pokos<TAB>where".
// Compiled next to CaveGen's classes (package-private access). Usage:
//   java -cp <cavegen build> SublevelItems CAVE SUBLEVEL 0xSEED [CAVE SUBLEVEL 0xSEED ...]
public class SublevelItems {
    public static void main(String[] args) {
        for (int a = 0; a + 2 < args.length; a += 3) {
            CaveGen.run(new String[] {"cave", args[a], args[a + 1], "-seed", args[a + 2], "-noimages", "-noprints", "-nostats"});
            CaveGen g = new CaveGen();   // regenerate with the same settings and keep the instance
            System.out.println("# " + args[a] + " " + args[a + 1] + " " + args[a + 2]);
            for (Item i : g.placedItems) {
                String n = i.itemName.toLowerCase();
                System.out.println(n + "\t" + Parser.pokos.getOrDefault(n, -1) + "\tground");
            }
            for (Teki t : g.placedTekis) {
                if (t.itemInside != null) {
                    String n = t.itemInside.toLowerCase();
                    System.out.println(n + "\t" + Parser.pokos.getOrDefault(n, -1) + "\tin " + t.tekiName);
                }
            }
        }
    }
}
