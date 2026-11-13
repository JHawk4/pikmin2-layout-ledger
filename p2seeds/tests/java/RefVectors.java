// Prints reference values from CaveGen's Seed.java for the Python port's tests.
// Built and run by p2seeds/tests/make_ref_vectors.py against vendor/CaveGen.
import java.util.Random;

public class RefVectors {
    public static void main(String[] args) {
        Seed s = new Seed();
        Random r = new Random(12345);
        StringBuilder sb = new StringBuilder("{\"cases\": [");
        for (int k = 0; k < 200; k++) {
            long seed = r.nextLong() & 0xffffffffL;
            int n = 5 + r.nextInt(16);
            long jumpN = r.nextInt(5000);
            float[] vs = s.seed_to_vel_vector((int) seed, n);
            if (k > 0) sb.append(",");
            sb.append("{\"seed\":").append(seed)
              .append(",\"n\":").append(n)
              .append(",\"jump\":").append(jumpN)
              .append(",\"next1\":").append(s.next_seed(seed))
              .append(",\"nextN\":").append(s.next_seed(seed, jumpN))
              .append(",\"vels\":[");
            for (int j = 0; j < n; j++) {
                if (j > 0) sb.append(",");
                sb.append(Float.toString(vs[j]));
            }
            sb.append("]}");
        }
        sb.append("]}");
        System.out.println(sb);
    }
}
