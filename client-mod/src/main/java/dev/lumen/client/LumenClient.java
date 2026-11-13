package dev.lumen.client;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.keybinding.v1.KeyBindingHelper;
import net.fabricmc.fabric.api.client.rendering.v1.HudRenderCallback;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.fabricmc.fabric.api.client.screen.v1.Screens;
import net.minecraft.client.CloudStatus;
import net.minecraft.client.GraphicsStatus;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.ParticleStatus;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.PauseScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.item.ItemStack;
import net.fabricmc.loader.api.FabricLoader;
import org.lwjgl.glfw.GLFW;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Collection;
import java.util.Deque;
import java.util.Properties;

/** Lightweight, client-only HUD and visual settings for Lumen's Fabric 1.21.1 profile. */
public final class LumenClient implements ClientModInitializer {
    private static final int FRAME_WINDOW = 90;
    private static final long[] FRAME_NANOS = new long[FRAME_WINDOW];
    private static final Deque<Long> LEFT_CLICKS = new ArrayDeque<>();
    private static final Deque<Long> RIGHT_CLICKS = new ArrayDeque<>();
    private static final Path CONFIG = FabricLoader.getInstance().getConfigDir().resolve("lumen-client.properties");

    private static int frameCursor;
    private static int frameCount;
    private static long lastFrameNanos;
    private static boolean leftWasDown;
    private static boolean rightWasDown;
    private static boolean hudVisible = true;
    private static boolean fpsEnabled = true;
    private static boolean cpsEnabled = true;
    private static boolean keysEnabled = true;
    private static boolean armorEnabled = true;
    private static boolean potionsEnabled = true;
    private static KeyMapping menuKey;
    private static KeyMapping hudKey;
    private static boolean launchPresetApplied;

    @Override
    public void onInitializeClient() {
        loadConfiguration();
        menuKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.lumen.open_menu", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_F6, "category.lumen"));
        hudKey = KeyBindingHelper.registerKeyBinding(new KeyMapping(
                "key.lumen.toggle_hud", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_F7, "category.lumen"));

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            if (client.player != null && !launchPresetApplied) {
                launchPresetApplied = true;
                String preset = System.getProperty("lumen.performance.preset", "balanced");
                if ("low_end".equalsIgnoreCase(preset)) applyLowEndPreset();
                else if ("balanced".equalsIgnoreCase(preset)) applyBalancedPreset();
            }
            while (menuKey.consumeClick()) client.setScreen(new LumenMenuScreen(client.screen));
            while (hudKey.consumeClick()) {
                hudVisible = !hudVisible;
                saveConfiguration();
            }
        });

        ScreenEvents.AFTER_INIT.register((client, screen, width, height) -> {
            if (screen instanceof TitleScreen || screen instanceof PauseScreen) {
                Button lumenButton = Button.builder(
                        net.minecraft.network.chat.Component.literal("LUMEN CLIENT"),
                        button -> client.setScreen(new LumenMenuScreen(screen)))
                        .bounds(Math.max(8, width - 142), 12, 132, 22)
                        .build();
                Screens.getButtons(screen).add(lumenButton);
            }
        });

        HudRenderCallback.EVENT.register(LumenClient::renderHud);
        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> saveConfiguration());
    }

    private static void renderHud(GuiGraphics graphics, net.minecraft.client.DeltaTracker delta) {
        Minecraft minecraft = Minecraft.getInstance();
        long now = System.nanoTime();
        if (lastFrameNanos != 0L) {
            FRAME_NANOS[frameCursor] = now - lastFrameNanos;
            frameCursor = (frameCursor + 1) % FRAME_WINDOW;
            frameCount = Math.min(frameCount + 1, FRAME_WINDOW);
        }
        lastFrameNanos = now;

        if (minecraft.screen != null || minecraft.options.hideGui || minecraft.player == null) {
            leftWasDown = false;
            rightWasDown = false;
            return;
        }
        trackClicks(minecraft);
        if (!hudVisible) return;

        int width = minecraft.getWindow().getGuiScaledWidth();
        int height = minecraft.getWindow().getGuiScaledHeight();
        int y = 8;
        if (fpsEnabled) {
            double frameMs = averageFrameMillis();
            String fpsText = frameCount < 2
                    ? "FPS " + minecraft.getFps()
                    : String.format("FPS %d  •  %.1f ms", minecraft.getFps(), frameMs);
            drawChip(graphics, minecraft, 8, y, fpsText);
            y += 22;
        }
        if (cpsEnabled) {
            drawChip(graphics, minecraft, 8, y,
                    "CPS  L " + LEFT_CLICKS.size() + "  /  R " + RIGHT_CLICKS.size());
        }
        if (keysEnabled) drawKeystrokes(graphics, minecraft, height);
        if (armorEnabled) drawArmor(graphics, minecraft, height);
        if (potionsEnabled) drawPotions(graphics, minecraft, width);
    }

    private static void drawChip(GuiGraphics graphics, Minecraft minecraft, int x, int y, String text) {
        int textWidth = minecraft.font.width(text);
        graphics.fill(x, y, x + textWidth + 14, y + 17, 0xEAF2B90B);
        graphics.fill(x, y, x + 2, y + 17, 0xFFFFD34D);
        graphics.drawString(minecraft.font, text, x + 7, y + 5, 0xFF111318, false);
    }

    private static double averageFrameMillis() {
        if (frameCount == 0) return 0;
        long total = 0;
        for (int i = 0; i < frameCount; i++) total += FRAME_NANOS[i];
        return total / (double) frameCount / 1_000_000.0;
    }

    private static void trackClicks(Minecraft minecraft) {
        long window = minecraft.getWindow().getWindow();
        long now = System.currentTimeMillis();
        boolean leftDown = GLFW.glfwGetMouseButton(window, GLFW.GLFW_MOUSE_BUTTON_1) == GLFW.GLFW_PRESS;
        boolean rightDown = GLFW.glfwGetMouseButton(window, GLFW.GLFW_MOUSE_BUTTON_2) == GLFW.GLFW_PRESS;
        if (leftDown && !leftWasDown) LEFT_CLICKS.addLast(now);
        if (rightDown && !rightWasDown) RIGHT_CLICKS.addLast(now);
        leftWasDown = leftDown;
        rightWasDown = rightDown;
        trimClicks(LEFT_CLICKS, now);
        trimClicks(RIGHT_CLICKS, now);
    }

    private static void trimClicks(Deque<Long> clicks, long now) {
        while (!clicks.isEmpty() && now - clicks.peekFirst() > 1000) clicks.removeFirst();
    }

    private static void drawKeystrokes(GuiGraphics g, Minecraft mc, int screenHeight) {
        long window = mc.getWindow().getWindow();
        int x = 10, y = screenHeight - 78, size = 20, gap = 3;
        drawKey(g, mc, window, "W", mc.options.keyUp.getKey().getValue(), x + size + gap, y);
        drawKey(g, mc, window, "A", mc.options.keyLeft.getKey().getValue(), x, y + size + gap);
        drawKey(g, mc, window, "S", mc.options.keyDown.getKey().getValue(), x + size + gap, y + size + gap);
        drawKey(g, mc, window, "D", mc.options.keyRight.getKey().getValue(), x + 2 * (size + gap), y + size + gap);
        drawKey(g, mc, window, "JUMP", mc.options.keyJump.getKey().getValue(),
                x, y + 2 * (size + gap), 3 * size + 2 * gap, 18);
    }

    private static void drawKey(GuiGraphics g, Minecraft mc, long window, String label, int key, int x, int y) {
        drawKey(g, mc, window, label, key, x, y, 20, 20);
    }

    private static void drawKey(GuiGraphics g, Minecraft mc, long window, String label,
                                int key, int x, int y, int width, int height) {
        boolean pressed = key > 0 && GLFW.glfwGetKey(window, key) == GLFW.GLFW_PRESS;
        g.fill(x, y, x + width, y + height, pressed ? 0xFFF2B90B : 0xC9151A20);
        g.fill(x, y, x + width, y + 1, 0xFFFFD34D);
        g.drawCenteredString(mc.font, label, x + width / 2, y + (height - 8) / 2,
                pressed ? 0xFF111318 : 0xFFF6F1E7);
    }

    private static void drawArmor(GuiGraphics g, Minecraft mc, int screenHeight) {
        LocalPlayer player = mc.player;
        if (player == null) return;
        Collection<ItemStack> armor = player.getInventory().getArmor();
        int x = 10, y = screenHeight / 2 - armor.size() * 10;
        for (ItemStack item : armor) {
            if (!item.isEmpty()) g.renderItem(item, x, y);
            y += 20;
        }
    }

    private static void drawPotions(GuiGraphics g, Minecraft mc, int screenWidth) {
        LocalPlayer player = mc.player;
        if (player == null) return;
        int y = 10;
        for (MobEffectInstance effect : player.getActiveEffects()) {
            String name = effect.getEffect().value().getDisplayName().getString();
            String level = effect.getAmplifier() > 0 ? " " + (effect.getAmplifier() + 1) : "";
            int seconds = Math.max(0, effect.getDuration() / 20);
            String duration = String.format("%d:%02d", seconds / 60, seconds % 60);
            String line = name + level + "  " + duration;
            int x = screenWidth - mc.font.width(line) - 18;
            g.fill(x - 5, y - 3, screenWidth - 8, y + 14, 0xB80B0D10);
            g.fill(x - 5, y - 3, x - 3, y + 14, 0xFFF2B90B);
            g.drawString(mc.font, line, x, y, 0xFFF6F1E7, true);
            y += 20;
        }
    }

    public static boolean isFpsEnabled() { return fpsEnabled; }
    public static boolean isCpsEnabled() { return cpsEnabled; }
    public static boolean isKeysEnabled() { return keysEnabled; }
    public static boolean isArmorEnabled() { return armorEnabled; }
    public static boolean isPotionsEnabled() { return potionsEnabled; }
    public static boolean isHudVisible() { return hudVisible; }

    public static void setHudVisible(boolean value) { hudVisible = value; saveConfiguration(); }
    public static void setFpsEnabled(boolean value) { fpsEnabled = value; saveConfiguration(); }
    public static void setCpsEnabled(boolean value) { cpsEnabled = value; saveConfiguration(); }
    public static void setKeysEnabled(boolean value) { keysEnabled = value; saveConfiguration(); }
    public static void setArmorEnabled(boolean value) { armorEnabled = value; saveConfiguration(); }
    public static void setPotionsEnabled(boolean value) { potionsEnabled = value; saveConfiguration(); }

    public static void applyLowEndPreset() {
        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft == null) return;
        minecraft.options.graphicsMode().set(GraphicsStatus.FAST);
        minecraft.options.cloudStatus().set(CloudStatus.OFF);
        minecraft.options.particles().set(ParticleStatus.MINIMAL);
        minecraft.options.renderDistance().set(Math.min(6, minecraft.options.renderDistance().get()));
        minecraft.options.simulationDistance().set(Math.min(4, minecraft.options.simulationDistance().get()));
        minecraft.options.entityDistanceScaling().set(0.5D);
        minecraft.options.framerateLimit().set(60);
        minecraft.options.ambientOcclusion().set(false);
        minecraft.options.save();
    }

    public static void applyBalancedPreset() {
        Minecraft minecraft = Minecraft.getInstance();
        if (minecraft == null) return;
        minecraft.options.graphicsMode().set(GraphicsStatus.FAST);
        minecraft.options.cloudStatus().set(CloudStatus.FAST);
        minecraft.options.particles().set(ParticleStatus.DECREASED);
        minecraft.options.renderDistance().set(Math.min(10, minecraft.options.renderDistance().get()));
        minecraft.options.simulationDistance().set(Math.min(6, minecraft.options.simulationDistance().get()));
        minecraft.options.entityDistanceScaling().set(0.75D);
        minecraft.options.framerateLimit().set(90);
        minecraft.options.save();
    }

    private static void loadConfiguration() {
        Properties properties = new Properties();
        if (Files.isRegularFile(CONFIG)) {
            try (InputStream input = Files.newInputStream(CONFIG)) {
                properties.load(input);
                hudVisible = Boolean.parseBoolean(properties.getProperty("hudVisible", "true"));
                fpsEnabled = Boolean.parseBoolean(properties.getProperty("fps", "true"));
                cpsEnabled = Boolean.parseBoolean(properties.getProperty("cps", "true"));
                keysEnabled = Boolean.parseBoolean(properties.getProperty("keystrokes", "true"));
                armorEnabled = Boolean.parseBoolean(properties.getProperty("armor", "true"));
                potionsEnabled = Boolean.parseBoolean(properties.getProperty("potions", "true"));
            } catch (IOException ignored) {
                // Keep safe defaults if the optional client HUD settings cannot be read.
            }
        }
    }

    private static void saveConfiguration() {
        Properties properties = new Properties();
        properties.setProperty("hudVisible", Boolean.toString(hudVisible));
        properties.setProperty("fps", Boolean.toString(fpsEnabled));
        properties.setProperty("cps", Boolean.toString(cpsEnabled));
        properties.setProperty("keystrokes", Boolean.toString(keysEnabled));
        properties.setProperty("armor", Boolean.toString(armorEnabled));
        properties.setProperty("potions", Boolean.toString(potionsEnabled));
        try {
            Files.createDirectories(CONFIG.getParent());
            try (OutputStream output = Files.newOutputStream(CONFIG)) {
                properties.store(output, "Lumen client display settings");
            }
        } catch (IOException ignored) {
            // A settings write must not interrupt gameplay.
        }
    }
}
