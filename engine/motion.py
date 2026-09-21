"""Video filtergraph construction (legacy zero-shake zoompan path, verbatim)."""

from . import assets


def build_video_filter(item, panel_img, aspect, dur, frames, fps):
    """Builds the [outv] filter chain. Identical math to the legacy engine."""
    is_shorts = (aspect == "9:16")
    panel_num = int(item.get('panel', 1))

    anim = item.get("animation", "zoom_in")
    ease = f"(1-cos(PI*on/{frames}))/2"

    z_in = f"1.0+(0.15*{ease})"
    z_out = f"1.15-(0.15*{ease})"
    zoom_expr = z_in if anim == "zoom_in" else z_out

    base_crop = "crop=iw:ih*0.8:0:ih*0.1"

    if is_shorts:
        if anim == "scroll":
            ease_t = f"(1-cos(PI*t/{dur}))/2"
            v_filter = f"[1:v]{base_crop},scale=1080:-2:flags=bicubic,pad=1080:max(ih\\,1920):0:0:color=black[p_base];[p_base]crop=1080:1920:0:'max(0, ih-1920)*{ease_t}',setsar=1[outv]"
        else:
            scale_ratio = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
            v_filter = f"[1:v]{base_crop},{scale_ratio},scale=2160:3840:flags=bicubic,zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s=2160x3840:fps={fps},scale=1080:1920:flags=bicubic,setsar=1[outv]"
    else:
        bg_filter = "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1[bg];"
        orig_w, orig_h = assets.get_image_dims(panel_img)
        crop_h = orig_h * 0.8
        target_w = int(1080 * (orig_w / crop_h))
        target_w += target_w % 2

        slide_dur = 0.5
        cx = "(1920-w)/2"
        dist = "(1920/2+w/2)"
        ease_slide = f"sin(min(t/{slide_dur}\\,1)*(PI/2))"

        if panel_num % 2 == 0:
            slide_x = f"max({cx}\\, 1920 - {dist}*{ease_slide})"
        else:
            slide_x = f"min({cx}\\, -w + {dist}*{ease_slide})"

        if anim == "scroll":
            ease_t = f"(1-cos(PI*t/{dur}))/2"
            scroll_h = int(target_w * (orig_h / orig_w))
            scroll_h += scroll_h % 2
            v_filter = f"{bg_filter}[1:v]{base_crop},scale={target_w}:{scroll_h}:flags=bicubic,pad={target_w}:max(ih\\,1080):0:0:color=black,crop={target_w}:1080:0:'max(0, ih-1080)*{ease_t}'[p_anim];[bg][p_anim]overlay=x='{slide_x}':y='(1080-h)/2':shortest=1,setsar=1[outv]"
        else:
            uw, uh = target_w * 2, 1080 * 2
            v_filter = f"{bg_filter}[1:v]{base_crop},scale={uw}:{uh}:flags=bicubic,zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':y='ih/2-(ih/zoom)/2':d={frames}:s={uw}x{uh}:fps={fps},scale={target_w}:1080:flags=bicubic[p_anim];[bg][p_anim]overlay=x='{slide_x}':y='(1080-h)/2':shortest=1,setsar=1[outv]"

    return v_filter
