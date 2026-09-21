"""Video filtergraph construction (legacy zero-shake zoompan path, verbatim).

Optional kwargs (src/out/bg/bg_chain/exact) exist for segment rendering in
segments.py; defaults reproduce the legacy per-clip filtergraph byte-for-byte.
"""

from . import assets


def build_video_filter(item, panel_img, aspect, dur, frames, fps,
                       src="1:v", out="outv", bg="0:v",
                       bg_chain=True, exact=False):
    """Builds the [out] filter chain. Identical math to the legacy engine.

    src/out/bg: stream labels (without brackets) for the panel image input,
    the final output, and the background input.
    bg_chain:   emit the [0:v]scale->[bg] preamble (False when the caller
                supplies a pre-scaled, per-panel split bg stream).
    exact:      append trim=end_frame + setpts so the chain emits exactly
                `frames` frames (required for concat in segment mode).
    """
    is_shorts = (aspect == "9:16")
    panel_num = int(item.get('panel', 1))

    anim = item.get("animation", "zoom_in")
    ease = f"(1-cos(PI*on/{frames}))/2"

    z_in = f"1.0+(0.15*{ease})"
    z_out = f"1.15-(0.15*{ease})"
    zoom_expr = z_in if anim == "zoom_in" else z_out

    base_crop = "crop=iw:ih*0.8:0:ih*0.1"

    src_l = f"[{src}]"
    if exact:
        tail = f"[_{out}_pre]"
        suffix = (f";[_{out}_pre]trim=end_frame={frames},"
                  f"setpts=PTS-STARTPTS[{out}]")
    else:
        tail = f"[{out}]"
        suffix = ""

    if is_shorts:
        if anim == "scroll":
            ease_t = f"(1-cos(PI*t/{dur}))/2"
            v_filter = (f"{src_l}{base_crop},scale=1080:-2:flags=bicubic,"
                        f"pad=1080:max(ih\\,1920):0:0:color=black[p_base];"
                        f"[p_base]crop=1080:1920:0:'max(0, ih-1920)*{ease_t}',"
                        f"setsar=1{tail}{suffix}")
        else:
            scale_ratio = ("scale=1080:1920:force_original_aspect_ratio="
                           "increase,crop=1080:1920")
            v_filter = (f"{src_l}{base_crop},{scale_ratio},"
                        f"scale=2160:3840:flags=bicubic,"
                        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':"
                        f"y='ih/2-(ih/zoom)/2':d={frames}:s=2160x3840:"
                        f"fps={fps},scale=1080:1920:flags=bicubic,setsar=1"
                        f"{tail}{suffix}")
    else:
        bg_filter = (f"[{bg}]scale=1920:1080:force_original_aspect_ratio="
                     f"increase,crop=1920:1080,setsar=1[bg];") if bg_chain else ""
        bg_use = "[bg]" if bg_chain else f"[{bg}]"
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
            v_filter = (f"{bg_filter}{src_l}{base_crop},"
                        f"scale={target_w}:{scroll_h}:flags=bicubic,"
                        f"pad={target_w}:max(ih\\,1080):0:0:color=black,"
                        f"crop={target_w}:1080:0:'max(0, ih-1080)*{ease_t}'"
                        f"[p_anim];{bg_use}[p_anim]overlay=x='{slide_x}':"
                        f"y='(1080-h)/2':shortest=1,setsar=1{tail}{suffix}")
        else:
            uw, uh = target_w * 2, 1080 * 2
            v_filter = (f"{bg_filter}{src_l}{base_crop},"
                        f"scale={uw}:{uh}:flags=bicubic,"
                        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom)/2':"
                        f"y='ih/2-(ih/zoom)/2':d={frames}:s={uw}x{uh}:"
                        f"fps={fps},scale={target_w}:1080:flags=bicubic"
                        f"[p_anim];{bg_use}[p_anim]overlay=x='{slide_x}':"
                        f"y='(1080-h)/2':shortest=1,setsar=1{tail}{suffix}")

    return v_filter
