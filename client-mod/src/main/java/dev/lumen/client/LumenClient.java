package dev.lumen.client;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import org.lwjgl.glfw.GLFW;

import java.io.IOException;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Client-only, purely informational: draws FPS/frametime and (optionally) records frametimes
 * to CSV for the launcher's benchmark tool. It reads no world data and changes no gameplay.
 *
 * Benchmark mode: launch with -Dlumen.bench=/path/to/frametimes.csv
 *
 * NOTE: written against 1.21.1 (Mojang mappings). HudRenderCallback is deprecated in newer
 * Fabric API versions; port to the HUD element API when you bump Minecraft.
 */
public final class LumenClient implements ClientModInitializer {
    private static final int WINDOW = 120;
    private static final long[] ring = new long[WINDOW];
    private static int ringPos = 0, ringCount = 0;
    private static long lastNanos = 0;
    private static boolean hudVisible = true;
    private static KeyMapping toggleKey;

    private static final String BENCH_PATH = System.getProperty("lumen.bench");
    private static final List<Long> bench = new ArrayList<>();

    @Override
    public void onInitializeClient() {
        toggleKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.lumen.toggle_hud", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_F6, "category.lumen"));

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (toggleKey.consumeClick()) hudVisible = !hudVisible;
        });
        HudRenderCallback.EVENT.register(LumenClient::onHud);
        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> flushBench());
    }

    private static void onHud(GuiGraphics g, DeltaTracker delta) {
        long now = System.nanoTime();
        if (lastNanos != 0) {
            long dt = now - lastNanos;
            ring[ringPos] = dt;
            ringPos = (ringPos + 1) % WINDOW;
            ringCount = Math.min(ringCount + 1, WINDOW);
            if (BENCH_PATH != null) synchronized (bench) { bench.add(dt); }
        }
        lastNanos = now;

        Minecraft mc = Minecraft.getInstance();
        if (!hudVisible || mc.options.hideGui || ringCount < 2) return;

        long sum = 0, worst = 0;
        for (int i = 0; i < ringCount; i++) { sum += ring[i]; worst = Math.max(worst, ring[i]); }
        double avgMs = (sum / (double) ringCount) / 1_000_000.0;
        double fps = 1000.0 / avgMs;
        double worstMs = worst / 1_000_000.0;

        String text = String.format("FPS %.0f  |  %.1f ms  |  worst %.1f ms", fps, avgMs, worstMs);
        g.drawString(mc.font, text, 4, 4, 0xFFFFFFFF, true);
    }

    private static void flushBench() {
        if (BENCH_PATH == null) return;
        List<Long> copy;
        synchronized (bench) { copy = new ArrayList<>(bench); }
        if (copy.isEmpty()) return;
        try (PrintWriter w = new PrintWriter(Files.newBufferedWriter(Path.of(BENCH_PATH)))) {
            w.println("frame,ms");
            for (int i = 0; i < copy.size(); i++) w.printf("%d,%.4f%n", i, copy.get(i) / 1_000_000.0);
            long[] sorted = copy.stream().mapToLong(Long::longValue).sorted().toArray();
            int n = sorted.length;
            double avg = Arrays.stream(sorted).average().orElse(0) / 1e6;
            double p99 = sorted[Math.min(n - 1, (int) Math.ceil(n * 0.99) - 1)] / 1e6;
            w.printf("# frames=%d avg_ms=%.3f avg_fps=%.1f p99_ms=%.3f one_percent_low_fps=%.1f%n",
                    n, avg, 1000.0 / avg, p99, 1000.0 / p99);
        } catch (IOException ignored) {
            // benchmarking must never crash the game
        }
    }
}
