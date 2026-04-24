import random
from app.core.judges import create_blind_mapping


def test_deterministic_blind_mapping():
    """Two runs with same seed produce identical blind assignments."""
    models = [1, 2, 3, 4]
    random.seed(42)
    mapping_1 = create_blind_mapping(models)
    random.seed(42)
    mapping_2 = create_blind_mapping(models)
    assert mapping_1 == mapping_2


def test_different_seeds_different_mappings():
    """Different seeds produce different blind assignments."""
    models = [1, 2, 3, 4]
    random.seed(42)
    mapping_1 = create_blind_mapping(models)
    random.seed(99)
    mapping_2 = create_blind_mapping(models)
    assert mapping_1 != mapping_2
