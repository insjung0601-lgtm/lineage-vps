package solo;

import java.io.File;
import java.io.FileInputStream;
import java.util.Properties;

/** Live-reloaded solo settings: config/solo.properties (checked at most every 3 seconds). */
public final class SoloConfig {
    private static final File FILE = new File("config/solo.properties");
    private static volatile long lastCheck = 0;
    private static volatile long lastModified = -1;
    private static volatile int npcDamageRate = 100;
    private static volatile boolean fullHealPotion = true;
    private static volatile boolean openCastleGates = false;

    private SoloConfig() {}

    private static void refresh() {
        long now = System.currentTimeMillis();
        if (now - lastCheck < 3000) return;
        lastCheck = now;
        long mod = FILE.exists() ? FILE.lastModified() : 0;
        if (mod == lastModified) return;
        lastModified = mod;
        Properties p = new Properties();
        if (mod != 0) {
            try (FileInputStream in = new FileInputStream(FILE)) { p.load(in); } catch (Exception e) { return; }
        }
        try { npcDamageRate = Math.max(0, Math.min(1000, Integer.parseInt(p.getProperty("NpcDamageRate", "100").trim()))); } catch (Exception e) { npcDamageRate = 100; }
        String f = p.getProperty("FullHealPotion", "1").trim();
        fullHealPotion = f.equals("1") || f.equalsIgnoreCase("true");
        String g = p.getProperty("OpenCastleGates", "0").trim();
        openCastleGates = g.equals("1") || g.equalsIgnoreCase("true");
    }

    public static int npcDamageRate() { refresh(); return npcDamageRate; }
    public static boolean fullHealPotion() { refresh(); return fullHealPotion; }
    public static boolean openCastleGates() { refresh(); return openCastleGates; }
}
