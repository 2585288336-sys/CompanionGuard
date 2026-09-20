from __future__ import annotations

from companionguard_app.platform_ui import format_evaluation_layers_compact


def test_compact_layer_display_preserves_canonical_order_and_input():
    layers = ["layer3", "layer1", "layer1", "layer2"]

    assert format_evaluation_layers_compact(layers) == "L1 · L2 · L3"
    assert layers == ["layer3", "layer1", "layer1", "layer2"]


def test_compact_layer_display_covers_supported_combinations():
    assert format_evaluation_layers_compact(["layer2", "layer3"]) == "L2 · L3"
    assert format_evaluation_layers_compact(["layer2"]) == "L2"
    assert format_evaluation_layers_compact(["layer1", "layer3"]) == "L1 · L3"
