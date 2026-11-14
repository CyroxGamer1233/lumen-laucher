package dev.lumen.client;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;

/** Compact control center opened from the title/pause screen or with F6. */
public final class LumenMenuScreen extends Screen {
    private final Screen parent;

    public LumenMenuScreen(Screen parent) {
        super(Component.literal("Lumen Client"));
        this.parent = parent;
    }

    @Override
    protected void init() {
        int center = width / 2;
        int panelWidth = Math.min(520, Math.max(304, width - 20));
        int left = center - panelWidth / 2 + 12;
        int buttonWidth = (panelWidth - 32) / 2;
        int right = left + buttonWidth + 8;
        int top = height / 2 - 105;
        int buttonHeight = 20;
        int row = 24;

        addRenderableWidget(toggle("FPS HUD", LumenClient::isFpsEnabled,
                LumenClient::setFpsEnabled, left, top + 48, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("CPS counter", LumenClient::isCpsEnabled,
                LumenClient::setCpsEnabled, right, top + 48, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Keystrokes", LumenClient::isKeysEnabled,
                LumenClient::setKeysEnabled, left, top + 48 + row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Armor HUD", LumenClient::isArmorEnabled,
                LumenClient::setArmorEnabled, right, top + 48 + row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Potion HUD", LumenClient::isPotionsEnabled,
                LumenClient::setPotionsEnabled, left, top + 48 + 2 * row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("HUD visibility", LumenClient::isHudVisible,
                LumenClient::setHudVisible, right, top + 48 + 2 * row, buttonWidth, buttonHeight));

        addRenderableWidget(Button.builder(Component.literal("LOW-END • MAX FPS"),
                button -> LumenClient.applyLowEndPreset())
                .bounds(left, top + 126, buttonWidth, 22).build());
        addRenderableWidget(Button.builder(Component.literal("BALANCED"),
                button -> LumenClient.applyBalancedPreset())
                .bounds(right, top + 126, buttonWidth, 22).build());
        addRenderableWidget(Button.builder(Component.literal("DONE"),
                button -> onClose())
                .bounds(center - 70, top + 158, 140, 22).build());
    }

    private Button toggle(String name, BooleanSupplier getter, Consumer<Boolean> setter,
                          int x, int y, int width, int height) {
        return Button.builder(Component.literal(name + ": " + (getter.getAsBoolean() ? "ON" : "OFF")), button -> {
            boolean next = !getter.getAsBoolean();
            setter.accept(next);
            button.setMessage(Component.literal(name + ": " + (next ? "ON" : "OFF")));
        }).bounds(x, y, width, height).build();
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        renderBackground(graphics, mouseX, mouseY, partialTick);
        int panelWidth = Math.min(520, Math.max(304, width - 20));
        int panelHeight = 210;
        int left = (width - panelWidth) / 2;
        int top = (height - panelHeight) / 2 - 4;
        graphics.fill(left, top, left + panelWidth, top + panelHeight, 0xE9101318);
        graphics.fill(left, top, left + panelWidth, top + 3, 0xFFF2B90B);
        graphics.fill(left, top + 3, left + 1, top + panelHeight - 1, 0xAA59440C);
        graphics.fill(left + panelWidth - 1, top + 3, left + panelWidth, top + panelHeight - 1, 0xAA59440C);
        graphics.drawCenteredString(font, "LUMEN  •  CLIENT HUB",
                width / 2, top + 12, 0xFFFFD34D);
        String controls = width >= 420 ? "F6 HUB  •  F7 HUD  •  HUD + PERFORMANCE CONTROLS"
                : "HUD + PERFORMANCE CONTROLS";
        graphics.drawCenteredString(font, controls,
                width / 2, top + 30, 0xFFB7C0CC);
        String account = System.getProperty("lumen.account.name", "Offline profile");
        String skin = System.getProperty("lumen.skin.path", "");
        graphics.drawCenteredString(font,
                "Profile: " + account + "  •  Skin: " + (skin.isBlank() ? "default" : "local"),
                width / 2, top + panelHeight - 22, 0xFFB7C0CC);
        super.render(graphics, mouseX, mouseY, partialTick);
    }

    @Override
    public void onClose() {
        Minecraft.getInstance().setScreen(parent);
    }

    @Override
    public boolean isPauseScreen() {
        return true;
    }
}
