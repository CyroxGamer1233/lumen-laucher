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
        int left = center - 154;
        int right = center + 8;
        int top = height / 2 - 82;
        int buttonWidth = 146;
        int buttonHeight = 20;
        int row = 25;

        addRenderableWidget(toggle("FPS HUD", LumenClient::isFpsEnabled,
                LumenClient::setFpsEnabled, left, top, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("CPS counter", LumenClient::isCpsEnabled,
                LumenClient::setCpsEnabled, right, top, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Keystrokes", LumenClient::isKeysEnabled,
                LumenClient::setKeysEnabled, left, top + row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Armor HUD", LumenClient::isArmorEnabled,
                LumenClient::setArmorEnabled, right, top + row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("Potion HUD", LumenClient::isPotionsEnabled,
                LumenClient::setPotionsEnabled, left, top + 2 * row, buttonWidth, buttonHeight));
        addRenderableWidget(toggle("HUD visibility", LumenClient::isHudVisible,
                LumenClient::setHudVisible, right, top + 2 * row, buttonWidth, buttonHeight));

        addRenderableWidget(Button.builder(Component.literal("LOW-END • MAX FPS"),
                button -> LumenClient.applyLowEndPreset())
                .bounds(left, top + 4 * row, buttonWidth, 22).build());
        addRenderableWidget(Button.builder(Component.literal("BALANCED"),
                button -> LumenClient.applyBalancedPreset())
                .bounds(right, top + 4 * row, buttonWidth, 22).build());
        addRenderableWidget(Button.builder(Component.literal("DONE"),
                button -> onClose())
                .bounds(center - 70, top + 6 * row, 140, 22).build());
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
        int panelWidth = 340;
        int panelHeight = 215;
        int left = (width - panelWidth) / 2;
        int top = (height - panelHeight) / 2 - 4;
        graphics.fill(left, top, left + panelWidth, top + panelHeight, 0xE9101318);
        graphics.fill(left, top, left + panelWidth, top + 3, 0xFFF2B90B);
        graphics.drawCenteredString(font, "LUMEN  •  CLIENT CONTROL CENTER",
                width / 2, top + 12, 0xFFFFD34D);
        graphics.drawCenteredString(font, "F6 menu     •     F7 show/hide HUD",
                width / 2, top + 30, 0xFFB7C0CC);
        String account = System.getProperty("lumen.account.name", "Offline profile");
        graphics.drawCenteredString(font, "Profile: " + account, width / 2,
                top + panelHeight - 36, 0xFFB7C0CC);
        String skin = System.getProperty("lumen.skin.path", "");
        graphics.drawCenteredString(font,
                skin.isBlank() ? "Skin: default  •  choose one in Lumen Launcher"
                        : "Skin: local  •  change it in Lumen Launcher",
                width / 2, top + panelHeight - 23, 0xFFFFD34D);
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
