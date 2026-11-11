"""Curated TTS voice catalogs exposed by the CLI and Studio selectors.

Edge TTS and Azure Speech use the same short-name format, but they do not expose
the same catalog. Keep provider availability explicit so an Azure-only voice is
never offered to Edge TTS.
"""
from __future__ import annotations

# Verified against Microsoft's Azure Speech language/voice support table and
# edge_tts.list_voices() on 2026-08-06. Azure preview/region availability can
# change independently of this curated selector catalog.
CATALOG_VERIFIED_DATE = "2026-08-06"


def _voice(
    voice_id: str,
    label: str,
    locale: str,
    gender: str,
    *,
    model: str = "Standard",
    preview: bool = False,
) -> dict:
    voice = {
        "id": voice_id,
        "label": label,
        "locale": locale,
        "gender": gender,
        "model": model,
    }
    if preview:
        voice["preview"] = True
    return voice


# This is the current curated subset exposed through Edge's public TTS service.
# The two regional Mandarin voices are included because they are useful for
# mainland Chinese narration even though their locale is more specific than zh-CN.
EDGE_VOICE_OPTIONS = [
    _voice("zh-CN-XiaoxiaoNeural", "晓晓", "zh-CN", "Female"),
    _voice("zh-CN-XiaoyiNeural", "晓伊", "zh-CN", "Female"),
    _voice("zh-CN-YunjianNeural", "云健", "zh-CN", "Male"),
    _voice("zh-CN-YunxiNeural", "云希", "zh-CN", "Male"),
    _voice("zh-CN-YunxiaNeural", "云夏", "zh-CN", "Male"),
    _voice("zh-CN-YunyangNeural", "云扬", "zh-CN", "Male"),
    _voice("zh-CN-liaoning-XiaobeiNeural", "晓北（辽宁）", "zh-CN-liaoning", "Female"),
    _voice("zh-CN-shaanxi-XiaoniNeural", "晓妮（陕西）", "zh-CN-shaanxi", "Female"),
    _voice("en-US-JennyNeural", "Jenny", "en-US", "Female"),
    _voice("en-US-GuyNeural", "Guy", "en-US", "Male"),
    _voice("en-US-AriaNeural", "Aria", "en-US", "Female"),
    _voice("en-US-DavisNeural", "Davis", "en-US", "Male"),
    _voice("en-GB-SoniaNeural", "Sonia", "en-GB", "Female"),
    _voice("en-GB-RyanNeural", "Ryan", "en-GB", "Male"),
    _voice("en-AU-NatashaNeural", "Natasha", "en-AU", "Female"),
    _voice("en-AU-WilliamNeural", "William", "en-AU", "Male"),
]


# Azure supports the standard Edge personas above plus a substantially larger
# catalog. The additions below focus on current Simplified Chinese voices in
# mainland China: Mandarin, regional Mandarin, Wu, and mainland Cantonese.
AZURE_CHINA_EXCLUSIVE_VOICE_OPTIONS = [
    # HD, HD Flash, and HD Omni voices.
    _voice("zh-CN-Xiaoxiao:DragonHDFlashLatestNeural", "Xiaoxiao · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural", "Xiaoxiao 2 · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaochen:DragonHDLatestNeural", "Xiaochen · HD", "zh-CN", "Female", model="HD"),
    _voice("zh-CN-Xiaochen:DragonHDFlashLatestNeural", "Xiaochen · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaohan:DragonHDFlashLatestNeural", "Xiaohan · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoke:DragonHDFlashLatestNeural", "Xiaoke · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoshuang:DragonHDFlashLatestNeural", "Xiaoshuang · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoyi:DragonHDFlashLatestNeural", "Xiaoyi · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoyou:DragonHDFlashLatestNeural", "Xiaoyou · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Xiaoyu:DragonHDFlashLatestNeural", "Xiaoyu · HD Flash", "zh-CN", "Female", model="HD Flash"),
    _voice("zh-CN-Yunfan:DragonHDLatestNeural", "Yunfan · HD", "zh-CN", "Male", model="HD"),
    _voice("zh-CN-Yunhan:DragonHDFlashLatestNeural", "Yunhan · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Yunxi:DragonHDFlashLatestNeural", "Yunxi · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Yunxia:DragonHDFlashLatestNeural", "Yunxia · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Yunxiao:DragonHDFlashLatestNeural", "Yunxiao · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Yunye:DragonHDFlashLatestNeural", "Yunye · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Yunyi:DragonHDFlashLatestNeural", "Yunyi · HD Flash", "zh-CN", "Male", model="HD Flash"),
    _voice("zh-CN-Xiaoyue:DragonHDOmniLatestNeural", "Xiaoyue · HD Omni", "zh-CN", "Female", model="HD Omni", preview=True),
    _voice("zh-CN-Maroonallegro:DragonHDOmniLatestNeural", "Maroonallegro · HD Omni", "zh-CN", "Female", model="HD Omni", preview=True),
    _voice("zh-CN-Yunqi:DragonHDOmniLatestNeural", "Yunqi · HD Omni", "zh-CN", "Male", model="HD Omni", preview=True),

    # Multilingual personas.
    _voice("zh-CN-XiaochenMultilingualNeural", "Xiaochen · 多语言", "zh-CN", "Female", model="Multilingual"),
    _voice("zh-CN-XiaoshuangMultilingualNeural", "Xiaoshuang · 多语言", "zh-CN", "Female", model="Multilingual"),
    _voice("zh-CN-XiaoxiaoMultilingualNeural", "Xiaoxiao · 多语言", "zh-CN", "Female", model="Multilingual"),
    _voice("zh-CN-XiaoyouMultilingualNeural", "Xiaoyou · 多语言", "zh-CN", "Female", model="Multilingual"),
    _voice("zh-CN-XiaoyuMultilingualNeural", "Xiaoyu · 多语言", "zh-CN", "Female", model="Multilingual"),
    _voice("zh-CN-YunfanMultilingualNeural", "Yunfan · 多语言", "zh-CN", "Male", model="Multilingual"),
    _voice("zh-CN-YunxiaoMultilingualNeural", "Yunxiao · 多语言", "zh-CN", "Male", model="Multilingual"),
    _voice("zh-CN-YunyiMultilingualNeural", "Yunyi · 多语言", "zh-CN", "Male", model="Multilingual"),

    # Additional standard Mandarin personas.
    _voice("zh-CN-XiaochenNeural", "Xiaochen", "zh-CN", "Female"),
    _voice("zh-CN-XiaohanNeural", "Xiaohan", "zh-CN", "Female"),
    _voice("zh-CN-XiaomengNeural", "Xiaomeng", "zh-CN", "Female"),
    _voice("zh-CN-XiaomoNeural", "Xiaomo", "zh-CN", "Female"),
    _voice("zh-CN-XiaoqiuNeural", "晓秋", "zh-CN", "Female"),
    _voice("zh-CN-XiaorouNeural", "Xiaorou", "zh-CN", "Female"),
    _voice("zh-CN-XiaoruiNeural", "Xiaorui", "zh-CN", "Female"),
    _voice("zh-CN-XiaoshuangNeural", "Xiaoshuang（童声）", "zh-CN", "Female"),
    _voice("zh-CN-XiaoxiaoDialectsNeural", "Xiaoxiao · 方言", "zh-CN", "Female"),
    _voice("zh-CN-XiaoyanNeural", "Xiaoyan", "zh-CN", "Female"),
    _voice("zh-CN-XiaoyouNeural", "Xiaoyou（童声）", "zh-CN", "Female"),
    _voice("zh-CN-XiaozhenNeural", "Xiaozhen", "zh-CN", "Female"),
    _voice("zh-CN-YunfengNeural", "Yunfeng", "zh-CN", "Male"),
    _voice("zh-CN-YunhaoNeural", "Yunhao", "zh-CN", "Male"),
    _voice("zh-CN-YunjieNeural", "Yunjie", "zh-CN", "Male"),
    _voice("zh-CN-YunyeNeural", "Yunye", "zh-CN", "Male"),
    _voice("zh-CN-YunzeNeural", "Yunze", "zh-CN", "Male"),

    # MAI Voice 2 public-preview personas.
    _voice("zh-CN-Bo:MAI-Voice-2", "Bo · MAI 2", "zh-CN", "Male", model="MAI Voice 2", preview=True),
    _voice("zh-CN-Bo:MAI-Voice-2-Flash", "Bo · MAI 2 Flash", "zh-CN", "Male", model="MAI Voice 2 Flash", preview=True),
    _voice("zh-CN-Lan:MAI-Voice-2", "Lan · MAI 2", "zh-CN", "Female", model="MAI Voice 2", preview=True),
    _voice("zh-CN-Lan:MAI-Voice-2-Flash", "Lan · MAI 2 Flash", "zh-CN", "Female", model="MAI Voice 2 Flash", preview=True),
    _voice("zh-CN-Mei:MAI-Voice-2", "Mei · MAI 2", "zh-CN", "Female", model="MAI Voice 2", preview=True),
    _voice("zh-CN-Mei:MAI-Voice-2-Flash", "Mei · MAI 2 Flash", "zh-CN", "Female", model="MAI Voice 2 Flash", preview=True),
    _voice("zh-CN-Wei:MAI-Voice-2", "Wei · MAI 2", "zh-CN", "Male", model="MAI Voice 2", preview=True),
    _voice("zh-CN-Wei:MAI-Voice-2-Flash", "Wei · MAI 2 Flash", "zh-CN", "Male", model="MAI Voice 2 Flash", preview=True),

    # Mainland regional and Chinese-language voices not in Edge's current list.
    _voice("zh-CN-guangxi-YunqiNeural", "Yunqi（广西）", "zh-CN-guangxi", "Male", preview=True),
    _voice("zh-CN-henan-YundengNeural", "Yundeng（河南）", "zh-CN-henan", "Male"),
    _voice("zh-CN-liaoning-YunbiaoNeural", "Yunbiao（辽宁）", "zh-CN-liaoning", "Male", preview=True),
    _voice("zh-CN-shandong-YunxiangNeural", "Yunxiang（山东）", "zh-CN-shandong", "Male"),
    _voice("zh-CN-sichuan-YunxiNeural", "Yunxi（四川）", "zh-CN-sichuan", "Male", preview=True),
    _voice("wuu-CN-XiaotongNeural", "Xiaotong（吴语）", "wuu-CN", "Female"),
    _voice("wuu-CN-YunzheNeural", "Yunzhe（吴语）", "wuu-CN", "Male"),
    _voice("yue-CN-XiaoMinNeural", "XiaoMin（粤语）", "yue-CN", "Female"),
    _voice("yue-CN-YunSongNeural", "YunSong（粤语）", "yue-CN", "Male"),
]


AZURE_VOICE_OPTIONS = [*EDGE_VOICE_OPTIONS, *AZURE_CHINA_EXCLUSIVE_VOICE_OPTIONS]
VOICE_OPTIONS_BY_PROVIDER = {
    "edge": EDGE_VOICE_OPTIONS,
    "azure": AZURE_VOICE_OPTIONS,
}

# Public API used by Studio. A provider-keyed mapping avoids duplicating shared
# voice IDs with conflicting single-provider tags.
VOICE_OPTIONS = VOICE_OPTIONS_BY_PROVIDER


def voices_for_provider(provider: str) -> list[dict]:
    return VOICE_OPTIONS_BY_PROVIDER.get(provider, [])


def voice_option(voice_id: str, provider: str | None = None) -> dict | None:
    catalogs = (
        [voices_for_provider(provider)]
        if provider
        else VOICE_OPTIONS_BY_PROVIDER.values()
    )
    return next(
        (item for catalog in catalogs for item in catalog if item["id"] == voice_id),
        None,
    )
