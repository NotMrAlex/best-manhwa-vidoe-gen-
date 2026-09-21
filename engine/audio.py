"""Audio mixing filtergraph construction (legacy amix path, verbatim)."""

from .assets import AUDIO_EXTS, find_asset


def build_mix(item, vols):
    """Returns (extra_inputs, amix_str).

    extra_inputs: sfx/transition files to append as -i inputs (indices 3+).
    amix_str: the audio filter chain producing [aout].
    """
    amix_str = f"[2:a]volume={vols['voice']}dB[v]"
    a_sources = ["[v]"]
    inputs = []
    idx = 3

    if item.get("sfx", "none") != "none":
        sfx_file = find_asset("assets/sfx", item['sfx'], AUDIO_EXTS)
        if sfx_file:
            inputs.append(sfx_file)
            amix_str += f";[{idx}:a]volume={vols['sfx']}dB[sfx]"
            a_sources.append("[sfx]")
            idx += 1

    if item.get("transition", "none") != "none":
        tr_file = find_asset("assets/transitions", item['transition'], AUDIO_EXTS)
        if tr_file:
            inputs.append(tr_file)
            amix_str += f";[{idx}:a]volume={vols['transition']}dB[tr]"
            a_sources.append("[tr]")
            idx += 1

    if len(a_sources) > 1:
        amix_str += f";{''.join(a_sources)}amix=inputs={len(a_sources)}:duration=first[aout]"
    else:
        amix_str = f"[2:a]volume={vols['voice']}dB[aout]"

    return inputs, amix_str
