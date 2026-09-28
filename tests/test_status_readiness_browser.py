from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "rozkalns_weather" / "static"
NAVIGATION = STATIC / "navigation_v1.js"
STATUS = STATIC / "status_v1.js"
CSS = STATIC / "accepted_ui.css"
SW = STATIC / "sw.js"


def _browser_binary() -> str:
    for candidate in ("google-chrome", "chromium", "chromium-browser"):
        binary = shutil.which(candidate)
        if binary:
            return binary
    raise AssertionError("A Chromium-family browser is required for the Status readiness proof")


def _run_browser(uri: str, *, width: int) -> str:
    completed = subprocess.run(
        [
            _browser_binary(),
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            f"--window-size={width},900",
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


def _write_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "status-readiness.html"
    fixture.write_text(
        f"""<!doctype html>
<html lang="lv" data-ui-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="stylesheet" href="{CSS.as_uri()}">
  <style>
    *{{box-sizing:border-box}} body{{margin:0}} .view{{display:none}} .view.active{{display:block}}
    main{{max-width:100%;padding:12px 13px 90px}} .status-readiness-row{{display:grid;grid-template-columns:minmax(0,1fr);gap:3px}}
    .status-source-row{{max-width:100%;overflow-wrap:anywhere}} .tabs{{display:flex}} .tabs button{{min-width:0;flex:1}}
  </style>
</head>
<body>
  <a class="skip-link" href="#overview">Skip</a>
  <main>
    <section id="overview" class="view active"><h1>Overview</h1></section>
    <section id="models" class="view"><h1>Models</h1></section>
    <section id="safety" class="view"><h1>Radar</h1></section>
    <section id="accuracy" class="view"><h1>Accuracy</h1></section>
    <section id="status" class="view">
      <h1>Status &amp; Sources</h1>
      <select id="forecastLocation"><option value="station_05480" selected>station</option></select>
      <section id="statusWeatherNext" data-state="loading">
        <div id="statusWeatherNextState" class="surface-state state-loading"></div>
        <div class="status-readiness-row"><strong id="statusWeatherNextForecast">—</strong><span id="statusWeatherNextForecastMeta"></span></div>
        <div class="status-readiness-row"><strong id="statusWeatherNextVerification">—</strong><span id="statusWeatherNextVerificationMeta"></span></div>
      </section>
      <div id="statusSources"></div>
    </section>
  </main>
  <nav class="tabs">
    <button data-view="overview" class="active">Overview</button><button data-view="models">Models</button>
    <button data-view="safety">Radar</button><button data-view="accuracy">Accuracy</button><button data-view="status">Status</button>
  </nav>
  <output id="proof"></output>
  <script>
    document.querySelectorAll('.tabs button[data-view]').forEach((button)=>{{button.onclick=()=>{{
      document.querySelectorAll('.view').forEach((view)=>view.classList.toggle('active',view.id===button.dataset.view));
      document.querySelectorAll('.tabs button[data-view]').forEach((item)=>item.classList.toggle('active',item===button));
    }}}});
    const scenario = new URLSearchParams(location.search).get('scenario') || 'pending';
    const calls = [];
    const publicProviders = [
      {{id:'dwd_observations',model_name:'DWD observations',freshness_state:'fresh',ingest_state:'ready',last_retrieved_at_utc:'2026-09-28T13:00:00Z'}},
      {{id:'dwd_mosmix_l',model_name:'DWD MOSMIX-L',freshness_state:'fresh',ingest_state:'ready',last_retrieved_at_utc:'2026-09-28T13:00:00Z'}},
      {{id:'icon_d2',model_name:'ICON-D2',freshness_state:'fresh',ingest_state:'ready',last_retrieved_at_utc:'2026-09-28T13:00:00Z'}},
      {{id:'ecmwf_ifs',model_name:'ECMWF IFS',freshness_state:'fresh',ingest_state:'ready',last_retrieved_at_utc:'2026-09-28T13:00:00Z'}},
      {{id:'ecmwf_aifs',model_name:'ECMWF AIFS',freshness_state:'fresh',ingest_state:'ready',last_retrieved_at_utc:'2026-09-28T13:00:00Z'}}
    ];
    const wn = scenario === 'ready'
      ? {{id:'weathernext3',model_name:'WeatherNext 3',freshness_state:'fresh',ingest_state:'ready'}}
      : {{id:'weathernext3',model_name:'WeatherNext 3',freshness_state:'access_pending',ingest_state:'access_pending'}};
    const forecast = scenario === 'ready' ? {{series:[{{provider:'weathernext3',value:12.3,valid_time_utc:'2026-09-28T15:00:00Z',init_time_utc:'2026-09-28T12:00:00Z',lead_hours:3,retrieved_at_utc:'2026-09-28T13:05:00Z',statistic:'mean',model_version:'wn3-test'}}]}} : {{series:[]}};
    const verification = scenario === 'ready'
      ? {{verification_ready:true,truth_quality:{{reason_codes:[]}},providers:{{weathernext3:{{overall:{{n:12}}}}}},common_sample_slices:[{{provider:'weathernext3',sample_sufficiency_state:'sufficient'}}]}}
      : {{verification_ready:true,truth_quality:{{reason_codes:[]}},providers:{{}},common_sample_slices:[]}};
    window.fetch = async (url) => {{
      calls.push(String(url));
      if (String(url).includes('/api/health/providers')) return new Response(JSON.stringify({{providers:[...publicProviders,wn]}}),{{status:200,headers:{{'content-type':'application/json'}}}});
      if (String(url).includes('/api/hourly')) return new Response(JSON.stringify(forecast),{{status:200,headers:{{'content-type':'application/json'}}}});
      if (String(url).includes('/api/verification/summary')) return new Response(JSON.stringify(verification),{{status:200,headers:{{'content-type':'application/json'}}}});
      throw new Error('unexpected fetch '+url);
    }};
    setTimeout(()=>{{
      document.querySelector('[data-view="status"]').click();
      setTimeout(()=>{{
        const proof=document.querySelector('#proof');
        proof.dataset.scenario=scenario;
        proof.dataset.calls=String(calls.length);
        proof.dataset.forecast=document.querySelector('#statusWeatherNextForecast').textContent;
        proof.dataset.verification=document.querySelector('#statusWeatherNextVerification').textContent;
        proof.dataset.state=document.querySelector('#statusWeatherNext').dataset.state;
        proof.dataset.weathernextInPublicSources=String(document.querySelector('#statusSources').textContent.includes('WeatherNext'));
        proof.dataset.publicSourceCount=String(document.querySelectorAll('#statusSources .status-source-row').length);
        proof.dataset.noOverflow=String(document.documentElement.scrollWidth<=document.documentElement.clientWidth+1);
        proof.dataset.ready='true';
      }},250);
    }},40);
  </script>
  <script src="{NAVIGATION.as_uri()}"></script>
</body>
</html>"""
    )
    return fixture


def test_status_module_is_lazy_cached_and_uses_existing_contracts() -> None:
    navigation = NAVIGATION.read_text()
    status = STATUS.read_text()
    worker = SW.read_text()

    assert 'new URL("status_v1.js", navigationScriptUrl)' in navigation
    assert 'if (viewId === "status") ensureStatusModule().catch(() => {});' in navigation
    assert '"/static/status_v1.js"' in worker
    assert 'const CACHE = "rozkalns-weather-v21"' in worker
    assert '/api/health/providers' in status
    assert '/api/hourly?hours=48&variable=temperature_2m' in status
    assert '/api/verification/summary?days=30' in status
    assert 'No WeatherNext value is inferred from another provider.' in status


def test_status_browser_separates_forecast_availability_from_verification_readiness(tmp_path: Path) -> None:
    fixture = _write_fixture(tmp_path)
    for width in (384, 412):
        pending = _run_browser(f"{fixture.as_uri()}?scenario=pending#overview", width=width)
        assert 'data-ready="true"' in pending, pending
        assert 'data-scenario="pending"' in pending, pending
        assert 'data-calls="3"' in pending, pending
        assert 'data-forecast="No genuine data · access pending"' in pending, pending
        assert 'data-verification="Not ready · no WeatherNext verified samples"' in pending, pending
        assert 'data-weathernext-in-public-sources="false"' in pending, pending
        assert 'data-public-source-count="5"' in pending, pending
        assert 'data-no-overflow="true"' in pending, pending

        ready = _run_browser(f"{fixture.as_uri()}?scenario=ready#overview", width=width)
        assert 'data-ready="true"' in ready, ready
        assert 'data-scenario="ready"' in ready, ready
        assert 'data-calls="3"' in ready, ready
        assert 'data-forecast="Available · 12.3°"' in ready, ready
        assert 'data-verification="Ready · 1 sufficient cohort"' in ready, ready
        assert 'data-state="fresh"' in ready, ready
        assert 'data-weathernext-in-public-sources="false"' in ready, ready
        assert 'data-public-source-count="5"' in ready, ready
        assert 'data-no-overflow="true"' in ready, ready
