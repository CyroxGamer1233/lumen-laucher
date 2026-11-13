package dev.lumen.client.mixin;

import com.mojang.blaze3d.platform.NativeImage;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.AbstractClientPlayer;
import net.minecraft.client.renderer.texture.DynamicTexture;
import net.minecraft.client.resources.PlayerSkin;
import net.minecraft.resources.ResourceLocation;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

/** Uses the PNG selected in Lumen's Skins tab for this local profile only. */
@Mixin(AbstractClientPlayer.class)
public abstract class OfflineSkinMixin {
    private static final ResourceLocation LUMEN_SKIN_ID =
            ResourceLocation.fromNamespaceAndPath("lumen", "offline_skin");
    private static boolean lumen$attempted;
    private static ResourceLocation lumen$texture;

    @Inject(method = "getSkin", at = @At("HEAD"), cancellable = true)
    private void lumen$useLocalSkin(CallbackInfoReturnable<PlayerSkin> callback) {
        String profileUuid = System.getProperty("lumen.skin.uuid", "");
        String skinPath = System.getProperty("lumen.skin.path", "");
        if (profileUuid.isBlank() || skinPath.isBlank()) return;

        AbstractClientPlayer player = (AbstractClientPlayer) (Object) this;
        if (!player.getUUID().toString().equalsIgnoreCase(profileUuid)) return;

        ResourceLocation texture = lumen$loadTexture(Path.of(skinPath));
        if (texture == null) return;

        PlayerSkin vanilla = callback.getReturnValue();
        String modelName = System.getProperty("lumen.skin.model", "wide");
        PlayerSkin.Model model = "slim".equalsIgnoreCase(modelName)
                ? PlayerSkin.Model.SLIM : PlayerSkin.Model.WIDE;
        callback.setReturnValue(new PlayerSkin(
                texture, skinPath, vanilla.capeTexture(), vanilla.elytraTexture(), model, false));
    }

    private static ResourceLocation lumen$loadTexture(Path path) {
        if (lumen$attempted) return lumen$texture;
        lumen$attempted = true;
        if (!Files.isRegularFile(path)) return null;
        try {
            NativeImage image;
            try (InputStream input = Files.newInputStream(path)) {
                image = NativeImage.read(input);
            }
            if (image.getWidth() != 64 || image.getHeight() != 64) {
                image.close();
                return null;
            }
            Minecraft.getInstance().getTextureManager().register(
                    LUMEN_SKIN_ID, new DynamicTexture(image));
            lumen$texture = LUMEN_SKIN_ID;
            return lumen$texture;
        } catch (IOException | RuntimeException ignored) {
            return null;
        }
    }
}
