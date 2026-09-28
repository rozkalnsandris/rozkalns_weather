from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
ACCURACY = STATIC / "accuracy_v3.js"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the Accuracy summary proof")


def _run_browser(uri: str) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--window-size=412,892",
            "--virtual-time-budget=1800",
            "--dump-dom",
            uri,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_accuracy_summary_source_keeps_real_common_sample_contract() -> None:
    source = ACCURACY.read_text()
    worker = SW.read_text()

    assert 'row.variable === "temperature_2m"' in source
    assert 'ACCURACY_VARIABLE_UNITS = { temperature_2m: "°C" }' in source
    assert "row.matched_set_id" in source
    assert "row.missingness?.common_n" in source
    assert "WeatherNext 3 has no genuine common-sample row" in source
    assert "Rows remain provider-separated; no overall winner is inferred." in source
    assert "rain" not in source.split("ACCURACY_VARIABLE_UNITS", 1)[1].split(";", 1)[0]
    assert "wind" not in source.split("ACCURACY_VARIABLE_UNITS", 1)[1].split(";", 1)[0]
    assert 'const CACHE = "rozkalns-weather-v' in worker
    assert '"/static/accuracy_v3.js"' in worker


def test_accuracy_browser_switches_exact_common_sample_cohorts_without_demo_scores(tmp_path: Path) -> None:
    fixture = tmp_path / "accuracy-summary-proof.html"
    fixture.write_text(
        f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body>
  <div id="providerClasses"></div>
  <section class="panel">
    <div class="panel-title">Accuracy</div>
    <div id="accuracyTable"></div>
    <div id="leadBucketTable"></div>
  </section>
  <div id="calibrationTable"></div>
  <input id="drilldownMonth" type="month"><button id="loadDrilldown" type="button">load</button>
  <div id="drilldownDeterministic"></div><div id="drilldownEnsemble"></div>
  <output id="proof"></output>
  <script>
    const calls=[];
    const baseMissing=(n)=>({{common_n:n,missing_n:0,expected_n:n,available_n:n,excluded_non_common_n:0}});
    const summary={{
      verification_ready:true,
      variable:'temperature_2m',
      truth_quality:{{reason_codes:[]}},
      providers:{{}},
      common_sample_slices:[
        {{variable:'temperature_2m',lead_bucket:'0-6h',matched_set_id:'cohort-a',provider:'icon_d2',model_version:'icon-a',n:40,mae:1.4,rmse:1.8,bias:0.2,sample_sufficiency_state:'limited_sample',missingness:baseMissing(40),coverage_n:0,p10_p90_coverage:null}},
        {{variable:'temperature_2m',lead_bucket:'0-6h',matched_set_id:'cohort-a',provider:'ecmwf_ifs',model_version:'ifs-a',n:40,mae:1.2,rmse:1.6,bias:-0.1,sample_sufficiency_state:'limited_sample',missingness:baseMissing(40),coverage_n:0,p10_p90_coverage:null}},
        {{variable:'temperature_2m',lead_bucket:'6-12h',matched_set_id:'cohort-b',provider:'weathernext3',model_version:'wn3-real',n:35,mae:1.1,rmse:1.5,bias:0.0,sample_sufficiency_state:'limited_sample',missingness:baseMissing(35),coverage_n:0,p10_p90_coverage:null}},
        {{variable:'temperature_2m',lead_bucket:'6-12h',matched_set_id:'cohort-b',provider:'icon_d2',model_version:'icon-b',n:35,mae:1.3,rmse:1.7,bias:0.1,sample_sufficiency_state:'limited_sample',missingness:baseMissing(35),coverage_n:0,p10_p90_coverage:null}},
        {{variable:'temperature_2m',lead_bucket:'6-12h',matched_set_id:'cohort-b',provider:'ecmwf_ifs',model_version:'ifs-b',n:35,mae:1.2,rmse:1.6,bias:-0.1,sample_sufficiency_state:'limited_sample',missingness:baseMissing(35),coverage_n:0,p10_p90_coverage:null}}
      ]
    }};
    window.fetch=async(url)=>{{
      calls.push(String(url));
      if(String(url)==='/api/providers') return new Response(JSON.stringify({{providers:[]}}),{{status:200,headers:{{'content-type':'application/json'}}}});
      if(String(url).includes('/api/verification/summary')) return new Response(JSON.stringify(summary),{{status:200,headers:{{'content-type':'application/json'}}}});
      if(String(url).includes('/api/verification/precipitation')) return new Response(JSON.stringify({{probability:{{}},occurrence_threshold_mm_per_hour:0.1}}),{{status:200,headers:{{'content-type':'application/json'}}}});
      throw new Error('unexpected '+url);
    }};
  </script>
  <script src="{ACCURACY.as_uri()}"></script>
  <script>
    const proof=document.querySelector('#proof');
    window.accuracy(30).then(()=>{{
      const select=document.querySelector('#accuracyCohort');
      const text=document.querySelector('#accuracySummary').textContent;
      proof.dataset.calls=String(calls.length);
      proof.dataset.options=String(select.options.length);
      proof.dataset.firstLead=String(select.options[0].textContent.includes('0-6h') && select.options[0].textContent.includes('n=40'));
      proof.dataset.firstUnit=String(text.includes('1.40 °C') && text.includes('1.20 °C'));
      proof.dataset.firstNoWn=String(text.includes('WeatherNext 3 has no genuine common-sample row'));
      proof.dataset.noRanking=String(text.includes('no overall winner is inferred'));
      select.value='1';
      select.dispatchEvent(new Event('change',{{bubbles:true}}));
      const second=document.querySelector('#accuracySummary').textContent;
      proof.dataset.secondLead=String(second.includes('6-12h') && second.includes('common samples n=35'));
      proof.dataset.secondWn=String(second.includes('WeatherNext 3') && second.includes('wn3-real') && second.includes('1.10 °C'));
      proof.dataset.noDemo=String(!second.includes('168') && !second.includes('demonstrācijas'));
      proof.dataset.ready='true';
    }});
  </script>
</body></html>"""
    )

    rendered = _run_browser(fixture.as_uri())
    for attribute in (
        "first-lead",
        "first-unit",
        "first-no-wn",
        "no-ranking",
        "second-lead",
        "second-wn",
        "no-demo",
        "ready",
    ):
        assert f'data-{attribute}="true"' in rendered, rendered
    assert 'data-calls="3"' in rendered, rendered
    assert 'data-options="2"' in rendered, rendered
