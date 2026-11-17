import xml.etree.ElementTree as ET

import pytest

pytest_plugins = ["pytester"]

def _props(xml_path) -> dict[str, dict[str, str]]:
    root = ET.parse(xml_path).getroot()
    return {
        tc.get("name"): {p.get("name"): p.get("value") for p in tc.iter("property")}
        for tc in root.iter("testcase")
    }

def test_marker_writes_case_ids_and_keys(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_sample="""
        import pytest

        @pytest.mark.case("C142")
        def test_one(): pass

        @pytest.mark.case("C1", 2, "c3")
        @pytest.mark.case("C1")
        def test_many(): pass

        class TestGroup:
            @pytest.mark.case("C7")
            @pytest.mark.parametrize("x", [1, 2])
            def test_param(self, x): assert x == 1

        def test_plain(): pass
        """
    )
    result = pytester.runpytest("--junitxml=out.xml", "-o", "junit_family=xunit2")
    result.assert_outcomes(passed=4, failed=1)
    props = _props(pytester.path / "out.xml")
    assert props["test_one"] == {"case_id": "C142", "automation_key": "test_sample.py::test_one"}
    assert props["test_many"]["case_id"] == "C1,C2,C3"
    assert props["test_param[2]"] == {
        "case_id": "C7",
        "automation_key": "test_sample.py::TestGroup::test_param[2]",
    }
    assert props["test_plain"] == {"automation_key": "test_sample.py::test_plain"}

def test_marker_is_registered(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("import pytest\n@pytest.mark.case('C1')\ndef test_x(): pass\n")
    result = pytester.runpytest("--strict-markers")
    result.assert_outcomes(passed=1)

def test_invalid_case_id_is_a_usage_error(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("import pytest\n@pytest.mark.case('login')\ndef test_x(): pass\n")
    result = pytester.runpytest()
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*invalid case id 'login'*"])

def test_plugin_can_be_disabled(pytester: pytest.Pytester) -> None:
    pytester.makepyfile("def test_x(): pass\n")
    pytester.runpytest("-p", "no:testharbor", "--junitxml=out.xml")
    assert _props(pytester.path / "out.xml")["test_x"] == {}
