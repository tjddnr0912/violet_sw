from realestate_bot.regions_extra import REGION_GROUPS, group_of, METRO_PREFIXES


def test_group_of_by_prefix():
    assert group_of("11680") == "서울"      # 강남구
    assert group_of("41135") == "경기"      # 성남 분당
    assert group_of("26110") == "부산"
    assert group_of("27110") == "대구"
    assert group_of("28110") == "인천"
    assert group_of("29110") == "광주"
    assert group_of("30110") == "대전"
    assert group_of("31110") == "울산"
    assert group_of("36110") == "세종"


def test_group_of_unknown_prefix_is_etc():
    assert group_of("99999") == "기타"


def test_metro_prefixes_are_six_cities():
    assert set(METRO_PREFIXES) == {"26", "27", "28", "29", "30", "31"}
    # 광역시 prefix는 전부 REGION_GROUPS에 시명으로 등록돼 있다
    for p in METRO_PREFIXES:
        assert p in REGION_GROUPS
