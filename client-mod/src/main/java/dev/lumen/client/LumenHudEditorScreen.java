package dev.lumen.client;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;

/** In-game drag editor for the Lumen HUD widgets. */
public final class LumenHudEditorScreen extends Screen {
    private final Screen parent;
    private final List<WidgetBounds> widgets = new ArrayList<>();
    private WidgetBounds dragging;
    private double dragOffsetX;
    private double dragOffsetY;

    public LumenHudEditorScreen(Screen parent) {
        super(Component.literal("Lumen HUD Editor"));
        this.parent = parent;
    }

    @Override
    protected void init() {
        int bottom = height - 34;
        addRenderableWidget(Button.builder(Component.literal("DONE  •  ESC"),
                button -> onClose())
                .bounds(width / 2 - 70, bottom, 140, 22)
                .build());
        widgets.clear();
        widgets.add(widget("fps", "FPS / FRAME TIME", 8, 8, 126, 22));
        widgets.add(widget("cps", "CLICK COUNTER", 8, 30, 126, 22));
        widgets.add(widget("keys", "KEYSTROKES", 10, height - 78, 70, 70));
        widgets.add(widget("armor", "ARMOR HUD", 10, height / 2 - 40, 24, 84));
        widgets.add(widget("potions", "POTION HUD", width - 190, 10, 180, 34));
    }

    private WidgetBounds widget(String key, String label, int x, int y, int widgetWidth, int widgetHeight) {
        int left = clamp(LumenClient.hudX(key, x), 0, width - widgetWidth);
        int top = clamp(LumenClient.hudY(key, y), 0, height - widgetHeight);
        return new WidgetBounds(key, label, left, top, widgetWidth, widgetHeight);
    }

    @Override
    public void render(GuiGraphics graphics, int mouseX, int mouseY, float partialTick) {
        graphics.fill(0, 0, width, height, 0x5806080A);
        graphics.fill(0, 0, width, 42, 0xB9101318);
        graphics.drawCenteredString(font, "HUD EDITOR  •  DRAG WIDGETS TO MOVE",
                width / 2, 14, 0xFFFFD34D);

        for (WidgetBounds widget : widgets) {
            graphics.fill(widget.x, widget.y, widget.x + widget.width, widget.y + widget.height,
                    dragging == widget ? 0xDDF2B90B : 0xB9101318);
            int edge = dragging == widget ? 0xFFFFD34D : 0xFF8F7834;
            graphics.fill(widget.x, widget.y, widget.x + widget.width, widget.y + 1, edge);
            graphics.fill(widget.x, widget.y + widget.height - 1,
                    widget.x + widget.width, widget.y + widget.height, edge);
            graphics.fill(widget.x, widget.y, widget.x + 1, widget.y + widget.height, edge);
            graphics.fill(widget.x + widget.width - 1, widget.y,
                    widget.x + widget.width, widget.y + widget.height, edge);
            graphics.drawCenteredString(font, widget.label,
                    widget.x + widget.width / 2, widget.y + 7,
                    dragging == widget ? 0xFF111318 : 0xFFF6F1E7);
        }
        super.render(graphics, mouseX, mouseY, partialTick);
    }

    @Override
    public boolean mouseClicked(double mouseX, double mouseY, int button) {
        if (button == 0) {
            for (int index = widgets.size() - 1; index >= 0; index--) {
                WidgetBounds widget = widgets.get(index);
                if (widget.contains(mouseX, mouseY)) {
                    dragging = widget;
                    dragOffsetX = mouseX - widget.x;
                    dragOffsetY = mouseY - widget.y;
                    return true;
                }
            }
        }
        return super.mouseClicked(mouseX, mouseY, button);
    }

    @Override
    public boolean mouseDragged(double mouseX, double mouseY, int button,
                               double dragX, double dragY) {
        if (dragging != null && button == 0) {
            dragging.x = clamp((int) (mouseX - dragOffsetX), 0, width - dragging.width);
            dragging.y = clamp((int) (mouseY - dragOffsetY), 0, height - dragging.height);
            LumenClient.setHudPosition(dragging.key, dragging.x, dragging.y);
            return true;
        }
        return super.mouseDragged(mouseX, mouseY, button, dragX, dragY);
    }

    @Override
    public boolean mouseReleased(double mouseX, double mouseY, int button) {
        if (button == 0 && dragging != null) {
            dragging = null;
            LumenClient.saveHudConfiguration();
            return true;
        }
        return super.mouseReleased(mouseX, mouseY, button);
    }

    @Override
    public void onClose() {
        LumenClient.saveHudConfiguration();
        Minecraft.getInstance().setScreen(parent);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }

    private static int clamp(int value, int minimum, int maximum) {
        return Math.max(minimum, maximum < minimum ? minimum : Math.min(value, maximum));
    }

    private static final class WidgetBounds {
        private final String key;
        private final String label;
        private final int width;
        private final int height;
        private int x;
        private int y;

        private WidgetBounds(String key, String label, int x, int y, int width, int height) {
            this.key = key;
            this.label = label;
            this.x = x;
            this.y = y;
            this.width = width;
            this.height = height;
        }

        private boolean contains(double mouseX, double mouseY) {
            return mouseX >= x && mouseX <= x + width && mouseY >= y && mouseY <= y + height;
        }
    }
}
