from realestate_bot import config


def test_seoul_has_25_gu():
    assert len(config.SEOUL_GU) == 25


def test_all_codes_are_5_digit():
    for gu, code in config.SEOUL_GU.items():
        assert len(code) == 5 and code.isdigit(), f"{gu}={code}"


def test_mapo_code_matches_verified_value():
    # get_region_code('마포구') == '11440' (spike에서 검증)
    assert config.SEOUL_GU["마포구"] == "11440"


def test_all_regions_includes_seoul_and_expands():
    # ALL_REGIONS = 서울 25 + 경기/광역시/세종 (백필 대상)
    assert config.SEOUL_GU.items() <= config.ALL_REGIONS.items()  # 서울 포함
    assert len(config.ALL_REGIONS) > 100                          # 서울 25 + 신규 95
    for name, code in config.ALL_REGIONS.items():
        assert len(code) == 5 and code.isdigit(), f"{name}={code}"


def test_mcp_config_path_exists():
    import os
    assert os.path.exists(config.MCP_CONFIG_PATH), config.MCP_CONFIG_PATH
