from conftest import load_module


collector = load_module("collector_main", "services/collector-service/app/main.py")


def test_deterministic_value_is_stable() -> None:
    value_1 = collector.deterministic_value("sensor-a", 10)
    value_2 = collector.deterministic_value("sensor-a", 10)
    assert value_1 == value_2
    assert 60.0 <= value_1 <= 145.0


def test_parse_web_with_bs4_extracts_points() -> None:
    html = """
    <html>
      <body>
        <div class="reading">A1</div>
        <div class="reading">B2</div>
      </body>
    </html>
    """
    points = collector.parse_web_with_bs4(html, ".reading", max_points=10)
    assert len(points) == 2
    assert all(isinstance(v, float) for v in points)
