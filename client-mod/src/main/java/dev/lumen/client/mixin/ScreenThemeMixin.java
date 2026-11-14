package dev.lumen.client.mixin;

import dev.lumen.client.LumenMenuScreen;
import net.minecraft.client.gui.GuiGraphics;
import net.minecraft.client.gui.screens.Screen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(Screen.class)
public abstract class ScreenThemeMixin {
    @Shadow
    protected int width;

    @Shadow
    protected int height;

    @Inject(
            method = "renderBackground(Lnet/minecraft/client/gui/GuiGraphics;IIF)V",
            at = @At("TAIL")
    )
    private void lumen$applyUiAccent(GuiGraphics graphics, int mouseX, int mouseY,
                                     float partialTick, CallbackInfo callback) {
        if ((Object) this instanceof LumenMenuScreen) return;
        graphics.fill(0, 0, width, height, 0x1806080A);
        graphics.fill(0, 0, width, 2, 0xDDF2B90B);
    }
}
