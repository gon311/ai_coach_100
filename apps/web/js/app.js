const { createApp, reactive, computed } = Vue;

/* ============================================================
   MOCK DATA
   ============================================================ */

const ADULT_ITEMS = [
  { code: "cross_situp", name: "교차윗몸일으키기", unit: "회", why: "복부·코어 근지구력을 확인해요.", prep: "매트 또는 바닥에 깔 담요", space: "누울 수 있는 1.5m x 1m 공간", method: "무릎을 세우고 누운 뒤, 팔꿈치가 반대쪽 무릎에 닿도록 상체를 교차로 들어올려요.", caution: "목에 힘을 주지 말고 반동을 사용하지 마세요." },
  { code: "sit_and_reach", name: "앉아윗몸앞으로굽히기", unit: "cm", why: "허리·하체 뒤쪽 유연성을 확인해요.", prep: "줄자 또는 유연성 측정자, 벽", space: "다리를 뻗고 앉을 수 있는 공간", method: "다리를 펴고 앉아 상체를 천천히 앞으로 굽혀 손끝이 닿는 위치를 측정해요.", caution: "무릎을 굽히지 말고, 통증이 있으면 즉시 중단하세요.", note: "영점 기준: 발바닥 앞면을 0cm으로 두고, 발끝을 넘으면 +, 못 미치면 −로 기록해요." },
  { code: "standing_long_jump", name: "제자리멀리뛰기", unit: "cm", why: "하체 순발력을 확인해요.", prep: "줄자, 미끄럽지 않은 바닥", space: "착지 거리까지 2m 이상의 평평한 공간", method: "제자리에서 두 발로 최대한 멀리 뛰어 착지 지점까지의 거리를 측정해요.", caution: "착지 시 무릎에 힘을 주고 균형을 잃지 않도록 주의하세요." },
];

const SENIOR_ITEMS = [
  { code: "chair_stand", name: "의자에 앉았다 일어서기", unit: "회", why: "하지 근기능을 확인해요.", prep: "등받이 없는 안정된 의자", space: "의자 앞뒤로 여유 공간", method: "팔짱을 낀 채 정해진 시간 동안 앉았다 일어서기를 반복해요.", caution: "의자가 흔들리지 않는지 먼저 확인하세요.", note: "의자 좌면 높이: 무릎이 90도 정도로 굽혀지는 높이로 통일해야 결과가 일관돼요." },
  { code: "sit_and_reach", name: "앉아윗몸앞으로굽히기", unit: "cm", why: "허리·하체 뒤쪽 유연성을 확인해요.", prep: "줄자 또는 유연성 측정자", space: "다리를 뻗고 앉을 수 있는 공간", method: "다리를 펴고 앉아 상체를 천천히 앞으로 굽혀 손끝이 닿는 위치를 측정해요.", caution: "무릎을 굽히지 말고, 통증이 있으면 즉시 중단하세요.", note: "영점 기준: 발바닥 앞면을 0cm으로 두고, 발끝을 넘으면 +, 못 미치면 −로 기록해요." },
  { code: "two_min_step", name: "2분 제자리걷기", unit: "회", why: "심폐 지구력 관련 기능을 확인해요.", prep: "무릎 높이 표시 테이프", space: "제자리 걷기가 가능한 공간", method: "2분 동안 무릎을 정해진 높이까지 올리며 제자리 걷기를 반복해요.", caution: "어지러움이 느껴지면 즉시 중단하세요." },
  { code: "chair_sit_and_reach_3m", name: "의자에 앉아 3m 표적 돌아오기", unit: "초", why: "민첩성과 균형 관련 기능을 확인해요.", prep: "의자, 표적(콘 등), 줄자", space: "왕복 3m 이상의 통로", method: "의자에서 일어나 3m 앞 표적을 돌아 다시 앉기까지의 시간을 측정해요.", caution: "회전 시 미끄러지지 않도록 주의하세요." },
];

const GRIP_ITEM = { code: "grip_strength", name: "악력", unit: "kg", why: "상지 근력을 확인해요.", prep: "악력계", space: "서서 측정할 수 있는 공간", method: "악력계를 잡고 최대 힘으로 2회 측정해 더 큰 값을 기록해요.", caution: "손목을 비틀지 말고 팔을 몸에서 떨어뜨려 측정하세요." };
const AGILITY_ITEM = { code: "agility_shuttle", name: "10m 4회 왕복달리기", unit: "초", why: "빠르게 방향을 바꾸는 민첩성을 확인해요.", prep: "초시계, 출발선과 10m 지점 표시물 2개", space: "미끄럽지 않고 장애물이 없는 직선 10m 이상", method: "출발선에서 10m 표시까지 달려 선을 넘고 돌아오는 동작을 2번 반복해 총 40m 완료 시간을 기록해요.", caution: "실내 좁은 공간에서는 실시하지 마세요. 급정지·회전이 불안하거나 관절 통증이 있으면 센터 측정을 이용하세요." };

const MEASUREMENT_VIDEO_GUIDES = {
  sit_and_reach: { title: "앉아 윗몸 앞으로 굽히기", youtubeId: "ydKH9ybDUZ4", sourceUrl: "https://youtu.be/ydKH9ybDUZ4?si=NKT_LEDspm6YgiOI" },
  cross_situp: { title: "교차 윗몸일으키기", youtubeId: "j5sktGOVq1c", sourceUrl: "https://youtu.be/j5sktGOVq1c?si=tUW5C_eqJ8xMZUty" },
  standing_long_jump: { title: "제자리멀리뛰기", youtubeId: "lb3PMPb-ugY", sourceUrl: "https://youtu.be/lb3PMPb-ugY?si=uDEISAFK7Y64w4R2" },
  agility_shuttle: { title: "10m 4회 왕복달리기", youtubeId: "DmXC2eJomjM", sourceUrl: "https://youtu.be/DmXC2eJomjM?si=vhKHwkdKC4CTvUy9" },
  chair_stand: { title: "의자에 앉았다 일어서기", youtubeId: "CZWDbfpoYF4", sourceUrl: "https://youtu.be/CZWDbfpoYF4?si=jM2k6bejcuBRFaoa" },
  two_min_step: { title: "2분 제자리걷기", youtubeId: "aYdPb99PcOw", sourceUrl: "https://youtu.be/aYdPb99PcOw?si=uAtkVlDn54uAkf6d" },
  chair_sit_and_reach_3m: { title: "의자에 앉아 3m 표적 돌아오기", youtubeId: "xh_LPFeXJyw", sourceUrl: "https://youtu.be/xh_LPFeXJyw?si=C_4Wq6ehRbnxTU9_" },
};

// Shared inline component: kept in both standalone HTML entry points.
let measurementYouTubeApiPromise = null;
function loadMeasurementYouTubeApi() {
  if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
  if (measurementYouTubeApiPromise) return measurementYouTubeApiPromise;
  measurementYouTubeApiPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.async = true;
    const finish = error => {
      clearInterval(poll);
      clearTimeout(timeout);
      if (error) { script.remove(); reject(error); }
      else resolve(window.YT);
    };
    const poll = setInterval(() => {
      if (window.YT && window.YT.Player) finish();
    }, 100);
    const timeout = setTimeout(() => finish(new Error('YouTube 연결 시간이 초과되었습니다.')), 12000);
    script.onerror = () => finish(new Error('YouTube 연결을 확인해 주세요.'));
    document.head.appendChild(script);
  }).catch(error => { measurementYouTubeApiPromise = null; throw error; });
  return measurementYouTubeApiPromise;
}

const MeasurementVideoPlayer = {
  props: { guide: { type: Object, required: true } },
  data() { return { status: 'loading', message: '동영상을 불러오는 중입니다…', attempt: 0 }; },
  computed: {
    canEmbed() { return /^https?:$/.test(window.location.protocol); },
    watchUrl() { return 'https://www.youtube.com/watch?v=' + this.guide.youtubeId; },
    embedUrl() {
      if (!this.canEmbed) return '';
      const params = new URLSearchParams({ autoplay: '1', controls: '1', rel: '0', playsinline: '1', enablejsapi: '1', origin: window.location.origin });
      return 'https://www.youtube-nocookie.com/embed/' + this.guide.youtubeId + '?' + params;
    },
  },
  created() { this._player = null; this._requestVersion = 0; this._disposed = false; this._readyTimer = null; },
  mounted() {
    if (this.canEmbed) this.attachPlayer();
    else { this.status = 'external'; this.message = 'YouTube에서 영상을 열었습니다. 새 탭이 열리지 않았다면 아래 버튼을 눌러 주세요.'; }
  },
  beforeUnmount() { this._disposed = true; this._requestVersion += 1; this.stopPlayer(); },
  methods: {
    async attachPlayer() {
      const version = ++this._requestVersion;
      try {
        const YT = await loadMeasurementYouTubeApi();
        if (this._disposed || version !== this._requestVersion || !this.$refs.frame) return;
        this._readyTimer = setTimeout(() => {
          if (!this._disposed && version === this._requestVersion && this.status === 'loading') {
            this.status = 'error'; this.message = '영상 연결이 지연되고 있습니다. 다시 시도하거나 YouTube에서 재생해 주세요.';
          }
        }, 12000);
        const active = callback => event => { if (!this._disposed && version === this._requestVersion) callback(event); };
        this._player = new YT.Player(this.$refs.frame, {
          events: {
            onReady: active(() => {
              clearTimeout(this._readyTimer);
              if (this.status !== 'error') { this.status = 'ready'; this.message = '재생이 시작되지 않으면 영상 안의 ▶ 버튼을 눌러 주세요.'; }
            }),
            onStateChange: active(event => {
              if (event.data === 1) { clearTimeout(this._readyTimer); this.status = 'playing'; this.message = ''; }
            }),
            onError: active(event => this.handlePlayerError(event)),
            onAutoplayBlocked: active(() => this.handleAutoplayBlocked()),
          },
        });
      } catch (error) {
        if (this._disposed || version !== this._requestVersion) return;
        this.status = 'error'; this.message = '영상 연결을 확인하지 못했습니다. 영상의 재생 버튼을 누르거나 YouTube에서 열어 주세요.';
      }
    },
    handlePlayerError(event) {
      clearTimeout(this._readyTimer);
      this.status = 'error';
      const messages = {
        2: '영상 주소를 확인하지 못했습니다. YouTube에서 영상을 열어 주세요.',
        5: '이 브라우저에서 재생하지 못했습니다. YouTube에서 영상을 열어 주세요.',
        100: '영상이 비공개이거나 삭제되었을 수 있습니다. YouTube에서 확인해 주세요.',
        101: '이 영상은 외부 사이트 재생이 제한되어 있습니다. YouTube에서 시청해 주세요.',
        150: '이 영상은 외부 사이트 재생이 제한되어 있습니다. YouTube에서 시청해 주세요.',
        153: '이 실행 환경에서는 영상 재생을 허용하지 않습니다. YouTube에서 시청해 주세요.',
      };
      this.message = messages[event.data] || '영상을 재생하지 못했습니다. 다시 시도하거나 YouTube에서 열어 주세요.';
      console.warn('[measurement-video] YouTube error', event.data, this.guide.youtubeId);
    },
    handleAutoplayBlocked() {
      clearTimeout(this._readyTimer);
      if (this.status === 'error') return;
      this.status = 'ready'; this.message = '자동재생이 제한되었습니다. 영상 안의 ▶ 재생 버튼을 눌러 주세요.';
    },
    stopPlayer() {
      clearTimeout(this._readyTimer);
      if (this._player) { this._player.destroy(); this._player = null; }
    },
    retryPlayer() {
      this._requestVersion += 1;
      this.stopPlayer();
      this.status = 'loading'; this.message = '동영상을 다시 불러오는 중입니다…'; this.attempt += 1;
      this.$nextTick(() => { if (!this._disposed) this.attachPlayer(); });
    },
  },
  template: `
    <div class="fc-measure-video-player">
      <div v-if="canEmbed" :key="attempt" class="fc-measure-video-frame">
        <iframe ref="frame" :src="embedUrl" :title="guide.title+' 측정 방법 영상'"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>
      </div>
      <div v-else class="fc-measure-video-external">▶<br>측정 방법 영상</div>
      <p v-if="message" class="fc-measure-video-status" :class="{'is-error':status==='error'}" role="status" aria-live="polite">{{ message }}</p>
      <div class="fc-measure-video-actions">
        <button v-if="status==='error' && canEmbed" class="fc-measure-guide-btn" type="button" @click="retryPlayer">다시 시도</button>
        <a class="fc-measure-video-link" :href="watchUrl" target="_blank" rel="noopener">YouTube에서 영상 보기 ↗</a>
      </div>
    </div>
  `,
};

const RADAR_INPUT_ITEMS = [
  { code:"standing_long_jump", name:"제자리 멀리뛰기", unit:"cm" },
  { code:"cross_situp", name:"교차 윗몸 일으키기", unit:"회" },
  { code:"sit_and_reach", name:"앉아 윗몸 앞으로 굽히기", unit:"cm" },
  { code:"two_min_step", name:"2분 제자리걷기", unit:"회" },
  AGILITY_ITEM,
  GRIP_ITEM,
];

const CENTER_EXTRA_ITEMS = [
  { code: "grip_strength", name: "악력", unit: "kg" },
  { code: "cardio_endurance", name: "심폐지구력(센터 측정)", unit: "점" },
];

// PAR-Q — 공단 원문 확정본(사용자 제공, CONFIRMED)
const PARQ_QUESTIONS = [
  "의사에게 심장질환 진단을 받았거나, 신체활동/운동 삼가에 대한 말을 들은 적이 있습니까?",
  "운동을 할 때 가슴에 통증이 있습니까?",
  "지난달 휴식 시에도 가슴에 통증을 느낀 적이 있습니까?",
  "어지럼증으로 쓰러졌거나 의식을 잃은 적이 있습니까?",
  "운동할 때 심해질 수 있는 관절이나 뼈의 문제(예: 허리, 무릎 또는 고관절)가 있습니까?",
  "심장질환 등으로 의사에게 처방 받아 복용하는 약이 있습니까?",
  "신체활동/운동을 해서는 안되는 다른 이유가 있습니까?",
];

const NORM_PERIOD_NOTE = "규준 데이터 기준: 2022.01 ~ 2026.07 다년도 풀링(MOCK)";

const RANGE_WIDTH = { sit_and_reach: 10, cross_situp: 7, two_min_step: 7, standing_long_jump: 5, agility_shuttle: 5 };

const MOCK_CENTER_PERCENTILE = { cross_situp: 62, sit_and_reach: 68, standing_long_jump: 32, chair_stand: 55, two_min_step: 48, grip_strength: 58 };

function computeRange(code, center) {
  const w = RANGE_WIDTH[code];
  if (w == null) return null;
  const lo = Math.max(1, Math.round(center - w));
  const hi = Math.min(99, Math.round(center + w));
  return [lo, hi];
}

const PROGRESS_MAP = { landing: null, login: null, basicInfo: 10, routeSelect: 20, parq: 30, homeGuide: 42, measureInput: 55, measureProgress: 68, measureResult: 78, report: 88, recommend: 94, video: 100, centerInput: 60, centerGuidance: null };
const TITLE_MAP = { landing: "Landing", login: "Login", basicInfo: "기본정보", routeSelect: "측정 경로", parq: "PAR-Q", homeGuide: "홈 측정 가이드", measureInput: "결과 입력", measureProgress: "분석 중", measureResult: "결과 확인", report: "체력 리포트", recommend: "운동 추천", video: "운동 영상", centerInput: "센터 결과 입력", centerGuidance: "센터 안내" };

/* ============================================================
   VUE APP
   ============================================================ */

const App = {
  components: { MeasurementVideoPlayer },
  data() {
    return {
      page: "landing",
      form: { gender: "", age: "", height: "", weight: "" },
      route: null,
      parqAnswers: Array(7).fill(null),
      parqBlocked: false,
      gripOwned: null,
      homeValues: {},
      centerValues: {},
      openGuideIdx: 0,
      progressPct: 0,
      progressTimer: null,
      parqQuestions: PARQ_QUESTIONS,
      normPeriodNote: NORM_PERIOD_NOTE,
      apiStatus: "checking",
      apiStatusText: "AI 연결 확인 중",
      percentileResults: [],
      chartLoading: false,
      chartError: "",
      reportSummary: "",
      reportSummaryLoading: false,
      dbVideos: [],
      selectedVideoAxis: "",
      selectedVideoLabel: "",
      videoSidebarOpen: false,
      guideSidebarOpen: false,
      selectedMeasureGuide: null,
      measurementVideoSidebarOpen: false,
      selectedMeasurementVideo: null,
      videoLoading: false,
      videoError: "",
      chatSidebarOpen: false,
      chatInput: "",
      chatLoading: false,
      chatInitialized: false,
      chatMessages: [{role:"assistant",content:"체력 측정 결과나 운동 방법에 대해 물어보세요. E: 피트니스 하네스가 확인된 DB 근거 안에서 답변합니다."}],
    };
  },
  async mounted() {
    try {
      const response = await fetch('/api/health');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      this.apiStatus = data.status === 'ok' ? 'ok' : 'error';
      this.apiStatusText = data.status === 'ok' ? 'AI Fitness 연결됨' : 'AI 응답 이상';
    } catch (error) {
      this.apiStatus = 'error';
      this.apiStatusText = 'AI Fitness 연결 안 됨';
    }
  },
  computed: {
    ageGroup() { const age=Number(this.form.age); return age>=65?"senior":age>=19?"adult":age>=13?"teen":"youth"; },
    battery() { return this.ageMeasurementItems.filter(item=>item.code!=='grip_strength'); },
    ageMeasurementItems() {
      const codes=this.ageGroup==='senior'
        ? ['chair_stand','sit_and_reach','two_min_step','chair_sit_and_reach_3m']
        : (this.ageGroup==='adult'
          ? ['sit_and_reach','cross_situp','standing_long_jump','agility_shuttle']
          : ['sit_and_reach','standing_long_jump']);
      if(this.gripOwned===true)codes.push('grip_strength');
      const guides=[...ADULT_ITEMS,...SENIOR_ITEMS,AGILITY_ITEM,GRIP_ITEM];
      return codes.map(code=>guides.find(item=>item.code===code)).filter(Boolean);
    },
    homeMeasuredItems() { return this.ageMeasurementItems; },
    centerMeasuredItems() { return this.ageMeasurementItems; },
    reportItems() { return this.route === "CENTER" ? this.centerMeasuredItems : this.homeMeasuredItems; },
    reportValues() { return this.route === "CENTER" ? this.centerValues : this.homeValues; },
    basicInfoValid() { return this.form.gender && this.form.age && this.form.height && this.form.weight; },
    parqAnswered() { return this.parqAnswers.every(a => a !== null); },
    homeInputAllFilled() { return this.gripOwned!==null && this.homeMeasuredItems.every(it => this.homeValues[it.code] !== undefined && this.homeValues[it.code] !== "" && Number(this.homeValues[it.code]) >= 0); },
    centerInputAllFilled() { return this.centerMeasuredItems.every(it => this.centerValues[it.code] !== undefined && this.centerValues[it.code] !== "" && Number(this.centerValues[it.code]) >= 0); },
    unmeasuredList() {
      const list = [];
      if (this.route !== "HOME") return list;
      if (!this.gripOwned) list.push({ label: "근력", note: "악력계가 있으면 측정할 수 있어요." });
      if (this.ageGroup === "adult") list.push({ label: "심폐지구력", note: "44세 등 성인은 2분 제자리걷기 대신 센터의 왕복오래달리기·스텝검사로 측정해요." });
      else list.push({ label: "상지 근기능", note: "가까운 체력인증센터에서 측정할 수 있어요." }, { label: "협응력", note: "가까운 체력인증센터에서 측정할 수 있어요." });
      return list;
    },
    percentileRanked() {
      return this.reportItems
        .filter(it => it.code !== "cardio_endurance")
        .map(it => ({ name: it.name, pct: MOCK_CENTER_PERCENTILE[it.code] ?? 50 }))
        .sort((a, b) => b.pct - a.pct);
    },
    strongest() { return this.percentileRanked[0]; },
    weakest() { return this.percentileRanked[this.percentileRanked.length - 1]; },
    comparisonRows() {
      return this.reportItems
        .filter(it => it.code !== "cardio_endurance")
        .map(it => {
          const center = MOCK_CENTER_PERCENTILE[it.code] ?? 50;
          const topPct = 100 - center;
          const value = this.reportValues[it.code];
          if (this.route === "CENTER") {
            const r = [Math.max(1, topPct - 1), Math.min(99, topPct + 1)];
            return { code: it.code, name: it.name, unit: it.unit, value, mode: "point", text: `또래 상위 ${topPct}%`, range: r };
          }
          if (it.code === "chair_sit_and_reach_3m") {
            return { code: it.code, name: it.name, unit: it.unit, value, mode: "reference", text: "참고값 · 구간 폭 미확정", range: null };
          }
          if (it.code === "grip_strength") {
            const r = [Math.max(1, topPct - 1), Math.min(99, topPct + 1)];
            return { code: it.code, name: it.name, unit: it.unit, value, mode: "point", text: `또래 상위 ${topPct}% · 정식 백분위`, range: r };
          }
          const r = computeRange(it.code, center);
          if (!r) {
            return { code: it.code, name: it.name, unit: it.unit, value, mode: "reference", text: "참고값 · 구간 폭 미확정", range: null };
          }
          return { code: it.code, name: it.name, unit: it.unit, value, mode: "range", text: `또래 상위 ${100 - r[1]}~${100 - r[0]}%`, range: r };
        });
    },
    radarAxes() {
      const resultByCode = Object.fromEntries(this.percentileResults.map(item => [item.code, item]));
      const values = this.reportValues;
      const grip = Number(values.grip_strength || 0);
      const weight = Number(this.form.weight || 0);
      const gripRelative = weight > 0 ? Math.min(100, Math.max(0, grip / weight * 100)) : 0;
      const configs = [
        {label:"순발력", code:"POWER_LONGJUMP", valueCode:"standing_long_jump", unit:"cm", videoCategory:"power"},
        {label:"근지구력", code:"MUSC_END_SITUP", valueCode:"cross_situp", unit:"회", videoCategory:"endurance"},
        {label:"유연성", code:"FLEX_SIT_REACH", valueCode:"sit_and_reach", unit:"cm", videoCategory:"flexibility"},
        {label:"심폐지구력", code:"CARDIO_2MINSTEP", valueCode:"two_min_step", unit:"회", videoCategory:"cardio"},
        this.ageGroup==='senior'
          ? {label:"민첩성", code:"AGILITY_3M", valueCode:"chair_sit_and_reach_3m", unit:"초", videoCategory:"agility"}
          : {label:"민첩성", code:"AGILITY_10M_SHUTTLE", valueCode:"agility_shuttle", unit:"초", videoCategory:"agility"},
        {label:"악력", code:"GRIP_RELATIVE", valueCode:"grip_strength", unit:"kg", videoCategory:"grip"},
      ];
      return configs.map(axis => {
        const row = resultByCode[axis.code];
        const hasRawValue=values[axis.valueCode]!==undefined&&values[axis.valueCode]!==''&&Number.isFinite(Number(values[axis.valueCode]));
        const measured = axis.code === 'GRIP_RELATIVE' ? this.gripOwned===true&&hasRawValue : hasRawValue;
        const score = row && row.available ? 100 - Number(row.top_percent) : 0;
        const raw = axis.code === 'GRIP_RELATIVE' ? (grip ? `${grip}kg · 상대악력 ${gripRelative.toFixed(1)}%` : '미측정') : `${values[axis.valueCode] || '—'}${axis.unit}`;
        const chartRaw=axis.code==='GRIP_RELATIVE'?(grip?`${grip}kg`:'미측정'):(values[axis.valueCode]!==undefined&&values[axis.valueCode]!==''?`${values[axis.valueCode]}${axis.unit}`:'미측정');
        const chartAverage=row?.average_value!==null&&row?.average_value!==undefined?`${Number(row.average_value).toFixed(1)}${axis.code==='GRIP_RELATIVE'?'%':axis.unit}`:'없음';
        return {...axis, raw, chartRaw, chartAverage, measured, score:Math.min(100,Math.max(0,score)), topPercent:row?.top_percent, averageScore:row?.average_percentile ?? null, averageValue:row?.average_value, comparisonBand:row?.age_band, exactAgeMatch:row?.exact_age_match!==false, compared:Boolean(measured && row && row.available)};
      });
    },
    radarUserPoints() { return this.radarPoints(this.radarAxes.map(axis => axis.compared ? axis.score : 0)); },
    radarAveragePoints() { return this.radarPoints(this.radarAxes.map(axis => axis.averageValue!==null && axis.averageValue!==undefined ? axis.averageScore : 0)); },
    radarGridLevels() { return [20,40,60,80,100].map(level=>({level,points:this.radarPoints(this.radarAxes.map(()=>level))})); },
    radarUserDots() { return this.radarDotCoordinates(this.radarAxes.map(axis=>axis.compared?axis.score:null)); },
    radarAverageDots() { return this.radarDotCoordinates(this.radarAxes.map(axis=>axis.averageValue!==null&&axis.averageValue!==undefined?axis.averageScore:null)); },
    radarOuterPoints() { return this.radarPoints(this.radarAxes.map(()=>100)); },
    radarInnerPoints() { return this.radarPoints(this.radarAxes.map(()=>50)); },
    radarLabelPoints() {
      const count=this.radarAxes.length,center=150,radius=125;
      return this.radarAxes.map((axis,index)=>{const angle=-Math.PI/2+index*2*Math.PI/count;const x=center+Math.cos(angle)*radius;return {...axis,x,y:center+Math.sin(angle)*radius+4,axisX:center+Math.cos(angle)*94,axisY:center+Math.sin(angle)*94,anchor:x<center-10?'start':x>center+10?'end':'middle'}});
    },
    weakestHomeName() {
      const items = this.homeMeasuredItems.map(it => ({ name: it.name, pct: MOCK_CENTER_PERCENTILE[it.code] ?? 50 }));
      return items.sort((a, b) => a.pct - b.pct)[0]?.name;
    },
    progressLabel() { return TITLE_MAP[this.page]; },
    progressPctBar() { return PROGRESS_MAP[this.page]; },
  },
  methods: {
    go(next) { this.page = next; window.scrollTo(0, 0); },
    toggleGuide(i) { this.openGuideIdx = this.openGuideIdx === i ? -1 : i; },
    measurementVideoFor(item){return MEASUREMENT_VIDEO_GUIDES[item.code]||null;},
    showMeasureGuide(item){this.selectedMeasureGuide=item;this.guideSidebarOpen=true;this.measurementVideoSidebarOpen=false;this.videoSidebarOpen=false;this.chatSidebarOpen=false;},
    showMeasurementVideo(item) {
      const video = this.measurementVideoFor(item);
      if (!video) return;
      this.selectedMeasurementVideo = { ...video, measurementName: item.name };
      this.measurementVideoSidebarOpen = true;
      if ('guideSidebarOpen' in this) this.guideSidebarOpen = false;
      if ('videoSidebarOpen' in this) this.videoSidebarOpen = false;
      if ('chatSidebarOpen' in this) this.chatSidebarOpen = false;
      // file:// has no HTTP Referer. Open the original from the user click.
      if (!/^https?:$/.test(window.location.protocol)) window.open('https://www.youtube.com/watch?v=' + video.youtubeId, '_blank', 'noopener');
    },
    setParq(i, val) { this.parqAnswers[i] = val; },
    submitParq() {
      this.route = "HOME";
      if (this.parqAnswers.some(a => a === true)) { this.parqBlocked = true; this.go("centerGuidance"); }
      else { this.parqBlocked = false; this.go("measureInput"); }
    },
    startCenterRoute() { this.route = "CENTER"; this.go("centerInput"); },
    startProgress() {
      this.progressPct = 0;
      clearInterval(this.progressTimer);
      this.progressTimer = setInterval(() => {
        this.progressPct += 4;
        if (this.progressPct >= 100) {
          this.progressPct = 100;
          clearInterval(this.progressTimer);
          setTimeout(() => this.go("measureResult"), 350);
        }
      }, 45);
    },
    radarPoints(values) {
      const center=150,maxRadius=94,count=values.length;
      return values.map((value,index)=>{const angle=-Math.PI/2+index*2*Math.PI/count;const radius=maxRadius*Number(value||0)/100;return `${(center+Math.cos(angle)*radius).toFixed(1)},${(center+Math.sin(angle)*radius).toFixed(1)}`}).join(' ');
    },
    radarPointsAtIndices(values) {
      const center=150,maxRadius=94,count=values.length;
      return values.map((value,index)=>{if(value===null||value===undefined)return null;const angle=-Math.PI/2+index*2*Math.PI/count;const radius=maxRadius*Number(value||0)/100;return `${(center+Math.cos(angle)*radius).toFixed(1)},${(center+Math.sin(angle)*radius).toFixed(1)}`}).filter(Boolean).join(' ');
    },
    radarDotCoordinates(values) {
      const center=150,maxRadius=94,count=values.length;
      return values.map((value,index)=>{if(value===null||value===undefined)return null;const angle=-Math.PI/2+index*2*Math.PI/count;const radius=maxRadius*Number(value||0)/100;return {x:(center+Math.cos(angle)*radius).toFixed(1),y:(center+Math.sin(angle)*radius).toFixed(1)}}).filter(Boolean);
    },
    async loadPercentiles() {
      this.chartLoading=true;this.chartError="";
      const values=this.reportValues;
      const grip=Number(values.grip_strength),weight=Number(this.form.weight);
      const measurements={FLEX_SIT_REACH:Number(values.sit_and_reach),MUSC_END_SITUP:Number(values.cross_situp),CARDIO_2MINSTEP:Number(values.two_min_step),POWER_LONGJUMP:Number(values.standing_long_jump),AGILITY_10M_SHUTTLE:Number(values.agility_shuttle),AGILITY_3M:Number(values.chair_sit_and_reach_3m)};
      measurements.GRIP_RELATIVE=Number.isFinite(grip)&&grip>0&&Number.isFinite(weight)&&weight>0 ? grip/weight*100 : 0;
      Object.keys(measurements).forEach(key=>{if(!Number.isFinite(measurements[key]))delete measurements[key]});
      try {
        const response=await fetch('/api/center-percentiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({age:Number(this.form.age),sex:this.form.gender==='여성'?'F':'M',measurements})});
        const data=await response.json();if(!response.ok)throw new Error(data.detail||'DB 비교 실패');this.percentileResults=data.results||[];this.normPeriodNote=data.result_label;
      } catch(error) { this.chartError=String(error.message||error);this.percentileResults=[]; }
      finally { this.chartLoading=false; }
    },
    async loadReportSummary(){
      this.reportSummaryLoading=true;this.reportSummary='';
      const results=this.radarAxes.map(axis=>({label:axis.label,input:axis.raw,top_percent:axis.topPercent,average:axis.averageValue,age_band:axis.comparisonBand,compared:axis.compared}));
      try{const response=await fetch('/api/report-summary',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({age:Number(this.form.age),sex:this.form.gender,results})});const data=await response.json();if(!response.ok)throw new Error(data.detail||'요약 실패');this.reportSummary=data.summary||'';}catch(error){this.reportSummary='측정 결과 설명을 불러오지 못했습니다.';}finally{this.reportSummaryLoading=false;}
    },
    async openReport(){await this.loadPercentiles();this.go('report');this.loadReportSummary();},
    async showAxisVideos(category,label){
      this.selectedVideoAxis=category;this.selectedVideoLabel=label;this.videoSidebarOpen=true;this.guideSidebarOpen=false;this.measurementVideoSidebarOpen=false;this.chatSidebarOpen=false;this.dbVideos=[];this.videoLoading=true;this.videoError="";
      try{
        const response=await fetch(`/api/top-videos/${category}`);const data=await response.json();if(!response.ok)throw new Error(data.detail||'영상 DB 조회 실패');this.dbVideos=data.videos||[];
      }catch(error){this.videoError=String(error.message||error)}finally{this.videoLoading=false}
    },
    async openChat(){
      this.videoSidebarOpen=false;this.guideSidebarOpen=false;this.measurementVideoSidebarOpen=false;this.chatSidebarOpen=true;if(this.chatInitialized||this.chatLoading)return;
      this.chatLoading=true;
      const ranked=this.radarAxes.filter(axis=>axis.compared).slice().sort((a,b)=>Number(b.topPercent)-Number(a.topPercent));
      const focus=ranked[0]?.label||'전신 체력';
      const context=this.radarAxes.filter(axis=>axis.measured).map(axis=>`${axis.label} ${axis.raw}`).join(', ');
      try{
        const response=await fetch('/api/coach',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:'fitness-report-user',question:`${focus} 보완 운동을 추천해줘`,age:Number(this.form.age),sex:this.form.gender,height_cm:Number(this.form.height),weight_kg:Number(this.form.weight),goal:`${focus} 보완`,equipment:'없음',home_measurement_context:context})});
        const data=await response.json();if(!response.ok)throw new Error(data.detail||'하네스 준비 실패');
        const answer=data.answer||{};const intro=typeof answer==='string'?answer:[answer['운동명'],answer['추천이유'],answer['운동방법']].filter(Boolean).join('\n');
        this.chatMessages.push({role:'assistant',content:intro||'측정 결과를 바탕으로 대화 준비가 완료되었습니다. 궁금한 점을 물어보세요.'});this.chatInitialized=true;
      }catch(error){this.chatMessages.push({role:'assistant',content:'하네스 연결 오류: '+String(error.message||error)});}finally{this.chatLoading=false;}
    },
    async sendChat(){
      const message=this.chatInput.trim();if(!message||this.chatLoading||!this.chatInitialized)return;
      const history=this.chatMessages.slice(-6).map(item=>({role:item.role,content:item.content}));
      this.chatMessages.push({role:'user',content:message});this.chatInput='';this.chatLoading=true;
      try{
        const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:'fitness-report-user',message,history})});
        const data=await response.json();if(!response.ok)throw new Error(data.detail||'챗봇 응답 실패');this.chatMessages.push({role:'assistant',content:data.answer||'답변을 받지 못했습니다.'});
      }catch(error){this.chatMessages.push({role:'assistant',content:'챗봇 연결 오류: '+String(error.message||error)});}finally{this.chatLoading=false;}
    },
    goMeasureProgress() { this.go("measureProgress"); this.$nextTick(() => this.startProgress()); },
  },
  template: `
  <div class="fc-root">
    <div class="fc-phone">
      <div class="fc-topbar">
        <div class="fc-brand"><span class="fc-brand-mark"></span>체력코치 AI</div>
        <div style="display:flex;gap:8px;align-items:center"><span :class="['fc-badge', apiStatus==='ok' ? 'fc-badge-good' : 'fc-badge-warn']">{{ apiStatusText }}</span><span class="fc-step-label">{{ progressLabel }}</span></div>
      </div>
      <div class="fc-progress-track" v-if="progressPctBar !== null">
        <div class="fc-progress-fill" :style="{ width: progressPctBar + '%' }"></div>
      </div>

      <!-- LANDING -->
      <div class="fc-body" style="display:flex;flex-direction:column;justify-content:center;min-height:640px" v-if="page==='landing'">
        <span class="fc-badge fc-badge-primary">국민체육진흥공단 공공데이터 기반</span>
        <h1 class="fc-h1" style="margin-top:14px;font-size:28px">내 체력을 측정하고<br/>또래와 비교하고<br/>나에게 맞는 운동을 추천받아 보세요.</h1>
        <p class="fc-sub">국민체력100 공식 콘텐츠 기반 AI 체력코치, 체력코치 AI</p>
        <button class="fc-btn fc-btn-primary" @click="go('login')">체력 측정 시작하기</button>
      </div>

      <!-- LOGIN -->
      <div class="fc-body" v-if="page==='login'">
        <button class="fc-nav-back" @click="go('landing')">← 이전</button>
        <span class="fc-badge fc-badge-mock">MOCK — 실제 인증 미연동</span>
        <h1 class="fc-h1" style="margin-top:12px">로그인</h1>
        <p class="fc-sub">이번 MVP는 실제 인증 API가 연결되지 않아 로그인 흐름만 시연합니다.</p>
        <div class="fc-field"><label class="fc-label">아이디</label><input class="fc-input" value="demo_user" readonly /></div>
        <div class="fc-field"><label class="fc-label">비밀번호</label><input class="fc-input" type="password" value="mockpass" readonly /></div>
        <button class="fc-btn fc-btn-primary" @click="go('basicInfo')">Mock으로 로그인</button>
      </div>

      <!-- BASIC INFO -->
      <div class="fc-body" v-if="page==='basicInfo'">
        <button class="fc-nav-back" @click="go('login')">← 이전</button>
        <h1 class="fc-h1">기본정보</h1>
        <p class="fc-sub">체력 비교와 배터리 구성을 위해 최소 정보만 입력해요.</p>
        <div class="fc-field">
          <label class="fc-label">성별</label>
          <div class="fc-select-grid">
            <div :class="['fc-pill', form.gender==='여성' ? 'active':'']" @click="form.gender='여성'">여성</div>
            <div :class="['fc-pill', form.gender==='남성' ? 'active':'']" @click="form.gender='남성'">남성</div>
          </div>
        </div>
        <div class="fc-field"><label class="fc-label">연령(만 나이)</label><input class="fc-input" type="number" placeholder="예: 34" v-model="form.age" /></div>
        <div class="fc-field"><label class="fc-label">신장</label><div class="fc-input-row"><input class="fc-input" type="number" placeholder="170" v-model="form.height" /><span class="fc-unit">cm</span></div></div>
        <div class="fc-field"><label class="fc-label">체중</label><div class="fc-input-row"><input class="fc-input" type="number" placeholder="65" v-model="form.weight" /><span class="fc-unit">kg</span></div></div>
        <button class="fc-btn fc-btn-primary" :disabled="!basicInfoValid" @click="go('routeSelect')">다음</button>
      </div>

      <!-- ROUTE SELECT -->
      <div class="fc-body" v-if="page==='routeSelect'">
        <button class="fc-nav-back" @click="go('basicInfo')">← 이전</button>
        <h1 class="fc-h1">측정 경로 선택</h1>
        <p class="fc-sub">두 경로는 이후 동일한 리포트·추천 파이프라인으로 이어져요.</p>
        <div class="fc-route-card" @click="startCenterRoute">
          <span class="fc-badge fc-badge-good">CENTER</span>
          <h2 class="fc-h2" style="margin-top:10px">센터에서 측정했어요</h2>
          <p class="fc-sub" style="margin-bottom:0">국민체력100 센터의 공식 측정 결과를 입력해요. 근력·심폐지구력 등 전 항목이 포함될 수 있어요.</p>
        </div>
        <div class="fc-route-card" @click="go('parq')">
          <span class="fc-badge fc-badge-warn">HOME</span>
          <h2 class="fc-h2" style="margin-top:10px">집에서 직접 측정할게요</h2>
          <p class="fc-sub" style="margin-bottom:0">안전 문진(PAR-Q) 이후 자가측정을 진행해요. 근력·심폐지구력은 홈 배터리에 포함되지 않아요.</p>
        </div>
      </div>

      <!-- PAR-Q -->
      <div class="fc-body" v-if="page==='parq'">
        <button class="fc-nav-back" @click="go('routeSelect')">← 이전</button>
        <span class="fc-badge fc-badge-good">전신체상태설문지 원문 반영</span>
        <h1 class="fc-h1" style="margin-top:12px">PAR-Q 사전 문진</h1>
        <p class="fc-sub">자가측정 전 안전 확인을 위한 7문항이에요. 하나라도 '예'이면 자가측정 대신 센터 측정을 안내해요.</p>
        <div class="fc-parq-item" v-for="(q,i) in parqQuestions" :key="i">
          <div class="fc-parq-q">{{ i+1 }}. {{ q }}</div>
          <div class="fc-yn">
            <button :class="['no', parqAnswers[i]===false ? 'active':'']" @click="setParq(i,false)">아니오</button>
            <button :class="['yes', parqAnswers[i]===true ? 'active':'']" @click="setParq(i,true)">예</button>
          </div>
        </div>
        <button class="fc-btn fc-btn-primary" :disabled="!parqAnswered" @click="submitParq" style="margin-top:8px">제출하기</button>
      </div>

      <!-- HOME GUIDE -->
      <div class="fc-body" v-if="page==='homeGuide'">
        <button class="fc-nav-back" @click="go('parq')">← 이전</button>
        <h1 class="fc-h1">홈 측정 가이드</h1>
        <p class="fc-sub">{{ ageGroup==='senior' ? '어르신' : '성인' }} 홈 배터리 {{ battery.length }}종이에요. 항목을 눌러 방법을 확인하세요.</p>
        <div class="fc-card" v-for="(it,i) in battery" :key="it.code" @click="toggleGuide(i)" style="cursor:pointer">
          <div class="fc-guide-item-head">
            <h2 class="fc-h2" style="margin-bottom:0">{{ i+1 }}. {{ it.name }}</h2>
            <span>{{ openGuideIdx===i ? '▾' : '▸' }}</span>
          </div>
          <div v-if="openGuideIdx===i" style="margin-top:10px">
            <div class="fc-guide-row"><span class="fc-guide-label">왜</span>{{ it.why }}</div>
            <div class="fc-guide-row"><span class="fc-guide-label">준비물</span>{{ it.prep }}</div>
            <div class="fc-guide-row"><span class="fc-guide-label">공간</span>{{ it.space }}</div>
            <div class="fc-guide-row"><span class="fc-guide-label">방법</span>{{ it.method }}</div>
            <div class="fc-guide-row"><span class="fc-guide-label">주의</span>{{ it.caution }}</div>
            <div class="fc-card-soft" v-if="it.note" style="margin-top:8px;margin-bottom:0">
              <span class="fc-badge fc-badge-primary">측정 오차 핵심 기준</span>
              <p class="fc-sub" style="margin:8px 0 0">{{ it.note }}</p>
            </div>
          </div>
        </div>
        <div class="fc-card-soft">
          <h2 class="fc-h2">악력 (선택 모듈)</h2>
          <p class="fc-sub">악력계가 있으면 근력도 측정할 수 있어요.</p>
          <div class="fc-select-grid">
            <div :class="['fc-pill', gripOwned===true ? 'active':'']" @click="gripOwned=true">악력계 있어요</div>
            <div :class="['fc-pill', gripOwned===false ? 'active':'']" @click="gripOwned=false">없어요</div>
          </div>
        </div>
        <button class="fc-btn fc-btn-primary" :disabled="gripOwned===null" @click="go('measureInput')">측정 시작하기</button>
      </div>

      <!-- MEASURE INPUT (HOME) -->
      <div class="fc-body" v-if="page==='measureInput'">
        <button class="fc-nav-back" @click="go('parq')">← 이전</button>
        <h1 class="fc-h1">측정 결과 입력</h1>
        <p class="fc-sub">만 {{ form.age }}세 {{ form.gender }}에게 맞는 측정항목이에요. 각 가이드 버튼을 누르면 오른쪽에서 준비물과 측정 방법을 볼 수 있어요.</p>
        <div class="fc-card-soft">
          <h2 class="fc-h2">악력도 측정할까요?</h2>
          <div class="fc-select-grid"><div :class="['fc-pill',gripOwned===true?'active':'']" @click="gripOwned=true">악력계 있어요</div><div :class="['fc-pill',gripOwned===false?'active':'']" @click="gripOwned=false">측정하지 않아요</div></div>
        </div>
        <div class="fc-field" v-for="it in homeMeasuredItems" :key="it.code">
          <div class="fc-input-head"><label class="fc-label">{{ it.name }}</label><div class="fc-input-actions"><button type="button" class="fc-measure-guide-btn" @click="showMeasureGuide(it)">측정 가이드</button><button v-if="measurementVideoFor(it)" type="button" class="fc-measure-video-btn" @click="showMeasurementVideo(it)">▶ 동영상 가이드</button></div></div>
          <div class="fc-input-row">
            <input class="fc-input" type="number" placeholder="0" v-model="homeValues[it.code]" />
            <span class="fc-unit">{{ it.unit }}</span>
          </div>
        </div>
        <button class="fc-btn fc-btn-primary" :disabled="!homeInputAllFilled" @click="goMeasureProgress">입력 완료</button>
      </div>

      <!-- PROGRESS -->
      <div class="fc-body" style="display:flex;flex-direction:column;justify-content:center;align-items:center;min-height:500px;text-align:center" v-if="page==='measureProgress'">
        <div class="fc-progress-circle">{{ progressPct }}%</div>
        <h2 class="fc-h2">결과를 분석하고 있어요</h2>
        <p class="fc-sub">또래 비교 리포트를 준비하는 중이에요.</p>
      </div>

      <!-- MEASURE RESULT -->
      <div class="fc-body" v-if="page==='measureResult'">
        <h1 class="fc-h1">측정 결과 확인</h1>
        <p class="fc-sub">입력한 값을 확인하고 리포트로 이동하세요.</p>
        <div class="fc-card" style="display:flex;justify-content:space-between" v-for="it in homeMeasuredItems" :key="it.code">
          <span style="font-weight:600">{{ it.name }}</span>
          <span style="font-family:var(--mono)">{{ homeValues[it.code] }}{{ it.unit }}</span>
        </div>
        <button class="fc-btn fc-btn-primary" @click="openReport">리포트 보기</button>
      </div>

      <!-- CENTER INPUT -->
      <div class="fc-body" v-if="page==='centerInput'">
        <button class="fc-nav-back" @click="go('routeSelect')">← 이전</button>
        <span class="fc-badge fc-badge-good">CENTER</span>
        <h1 class="fc-h1" style="margin-top:10px">센터 측정 결과 입력</h1>
        <p class="fc-sub">국민체력100 센터에서 받은 측정 결과를 그대로 입력해요.</p>
        <div class="fc-card-soft">
          <h2 class="fc-h2">악력 측정도 입력할까요?</h2>
          <div class="fc-select-grid">
            <div :class="['fc-pill', gripOwned===true ? 'active':'']" @click="gripOwned=true">악력 포함</div>
            <div :class="['fc-pill', gripOwned===false ? 'active':'']" @click="gripOwned=false">악력 제외</div>
          </div>
        </div>
        <div class="fc-field" v-for="it in centerMeasuredItems" :key="it.code">
          <label class="fc-label">{{ it.name }}</label>
          <div class="fc-input-row">
            <input class="fc-input" type="number" placeholder="0" v-model="centerValues[it.code]" />
            <span class="fc-unit">{{ it.unit }}</span>
          </div>
        </div>
        <button class="fc-btn fc-btn-primary" :disabled="gripOwned===null || !centerInputAllFilled" @click="openReport">리포트 보기</button>
      </div>

      <!-- CENTER GUIDANCE -->
      <div class="fc-body" v-if="page==='centerGuidance'">
        <h1 class="fc-h1">체력인증센터 안내</h1>
        <div class="fc-card-soft" v-if="parqBlocked">
          <span class="fc-badge fc-badge-blocked">PAR-Q 1개 이상 '예'</span>
          <p class="fc-sub" style="margin:10px 0 0">서비스 이용 차단이 아니라, 안전한 측정 경로로 안내해 드려요.</p>
        </div>
        <div class="fc-card fc-radar-card">
          <h2 class="fc-h2">지금 이용 가능해요</h2>
          <button class="fc-btn fc-btn-outline" style="margin-bottom:8px" @click="go('centerInput')">센터 측정 결과 입력</button>
          <button class="fc-btn fc-btn-outline" style="margin-bottom:8px" @click="go('video')">공단 운동 영상 열람</button>
          <button class="fc-btn fc-btn-outline" @click="window.open('https://nfa.kspo.or.kr','_blank')">가까운 체력인증센터 찾기</button>
        </div>
        <div class="fc-card">
          <h2 class="fc-h2">지금은 잠겨 있어요</h2>
          <div class="fc-locked-row">🔒 자가측정</div>
          <div class="fc-locked-row">🔒 자동 운동처방</div>
          <div class="fc-locked-row">🔒 주간 루틴</div>
        </div>
        <p class="fc-disclaimer">본 리포트는 자가측정 기반 참고 정보이며, 국민체력100 공식 인증등급이 아닙니다. 의학적 진단을 대체하지 않습니다.</p>
      </div>

      <!-- REPORT -->
      <div class="fc-body" v-if="page==='report'">
        <h1 class="fc-h1">나의 체력 리포트</h1>
        <span class="fc-badge fc-badge-mock">{{ normPeriodNote }}</span>

        <div class="fc-section-divider"></div>
        <h2 class="fc-h2">측정항목 한눈에 보기</h2>
        <p class="fc-report-summary">{{ reportSummaryLoading ? 'Qwen3가 측정 결과를 간단히 정리하고 있습니다…' : reportSummary }}</p>
        <p class="fc-sub">주황색은 나, 초록 점선은 같은 성별·연령대의 평균이에요.</p>
        <div class="fc-card">
          <div v-if="chartLoading" class="fc-sub">측정 DB와 비교하는 중입니다…</div>
          <div v-else>
            <svg class="fc-radar" viewBox="0 0 300 300" role="img" :aria-label="radarAxes.map(axis=>axis.label).join(', ')+' 레이더 차트'">
              <defs><linearGradient id="userGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#ff9a62" stop-opacity=".42"/><stop offset="100%" stop-color="#f06432" stop-opacity=".12"/></linearGradient><linearGradient id="averageGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#8cbd68" stop-opacity=".26"/><stop offset="100%" stop-color="#4f8739" stop-opacity=".06"/></linearGradient><filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#233d27" flood-opacity=".13"/></filter></defs>
              <polygon v-for="grid in radarGridLevels" :key="grid.level" class="fc-radar-grid" :points="grid.points"/>
              <line v-for="point in radarLabelPoints" :key="'line-'+point.code" class="fc-radar-axis" x1="150" y1="150" :x2="point.axisX" :y2="point.axisY"/>
              <polygon class="fc-radar-average" :points="radarAveragePoints"/><polygon class="fc-radar-user" :points="radarUserPoints"/>
              <circle v-for="(dot,index) in radarAverageDots" :key="'avg-dot-'+index" class="fc-radar-dot-average" :cx="dot.x" :cy="dot.y" r="3.5"/><circle v-for="(dot,index) in radarUserDots" :key="'user-dot-'+index" class="fc-radar-dot-user" :cx="dot.x" :cy="dot.y" r="4"/>
              <circle class="fc-radar-center" cx="150" cy="150" r="3"/><text class="fc-radar-scale" x="154" y="135">20</text><text class="fc-radar-scale" x="154" y="116">40</text><text class="fc-radar-scale" x="154" y="97">60</text><text class="fc-radar-scale" x="154" y="78">80</text><text class="fc-radar-scale" x="154" y="59">100</text>
              <text v-for="point in radarLabelPoints" :key="'label-'+point.code" class="fc-radar-label" :x="point.x" :y="point.y" :text-anchor="point.anchor">{{ point.label }}</text>
              <text v-for="point in radarLabelPoints" :key="'value-'+point.code" class="fc-radar-axis-value" :x="point.x" :y="point.y+13" :text-anchor="point.anchor">나 {{ point.chartRaw }} · 평균 {{ point.chartAverage }}</text>
            </svg>
            <div class="fc-radar-legend"><span><i class="fc-radar-key" style="background:var(--cta)"></i>나의 측정</span><span><i class="fc-radar-key" style="background:var(--good)"></i>또래 평균</span></div>
            <div class="fc-metric-card" v-for="axis in radarAxes" :key="axis.code">
              <div class="fc-metric-head"><span class="fc-metric-name">{{ axis.label }}</span><button v-if="axis.measured" type="button" class="fc-guide-btn" :class="{active:selectedVideoAxis===axis.videoCategory && videoSidebarOpen}" @click="showAxisVideos(axis.videoCategory,axis.label)">동영상 가이드 보기</button></div>
              <div class="fc-metric-value">내 측정 {{ axis.raw }}<strong v-if="axis.compared"> · 상위 {{ Math.round(Number(axis.topPercent)) }}%</strong></div>
              <div class="fc-metric-compare">{{ axis.averageValue!==null && axis.averageValue!==undefined ? ('동일 성별·'+axis.comparisonBand+'세 평균 '+Number(axis.averageValue).toFixed(2)+(axis.code==='GRIP_RELATIVE'?'% (상대악력)':axis.unit)) : '해당 성별·연령대의 DB 평균이 없습니다.' }}</div>
            </div>
          </div>
          <p v-if="chartError" class="fc-error">{{ chartError }}</p>
        </div>

        <template v-if="unmeasuredList.length">
          <div class="fc-section-divider"></div>
          <h2 class="fc-h2">아직 측정하지 않은 항목</h2>
          <div class="fc-signal-list"><div class="fc-signal-row" v-for="u in unmeasuredList" :key="u.label"><i class="fc-signal-red"></i><span><strong>{{ u.label }}</strong> · {{ u.note }}</span></div></div>
        </template>

        <div class="fc-section-divider"></div>
        <h2 class="fc-h2">센터 측정 안내</h2>
        <button class="fc-btn fc-btn-outline" @click="go('centerGuidance')">가까운 체력인증센터 알아보기</button>

        <div class="fc-section-divider"></div>
        <h2 class="fc-h2">챗봇에게 물어보기</h2>
        <p class="fc-sub">Qwen3 4B와 E: 피트니스 근거 제한 하네스가 측정 결과와 운동 정보를 안내합니다.</p>
        <button class="fc-btn fc-btn-primary" @click="openChat">AI 체력 코치 챗봇 열기</button>

        <p class="fc-disclaimer">본 리포트는 자가측정 기반 참고 정보이며, 국민체력100 공식 인증등급이 아닙니다. 의학적 진단을 대체하지 않습니다.</p>
      </div>

      <!-- RECOMMEND -->
      <div class="fc-body" v-if="page==='recommend'">
        <button class="fc-nav-back" @click="go('report')">← 이전</button>
        <h1 class="fc-h1">오늘의 운동</h1>
        <span class="fc-badge fc-badge-good">측정 리포트 + DB 영상 연결</span>
        <div class="fc-section-divider"></div>
        <div class="fc-card">
          <span class="fc-badge fc-badge-primary">기본 구성</span>
          <h2 class="fc-h2" style="margin-top:8px">가벼운 유산소 걷기 10분</h2>
        </div>
        <div class="fc-card">
          <span class="fc-badge fc-badge-primary">기본 구성</span>
          <h2 class="fc-h2" style="margin-top:8px">코어 안정화 플랭크 3세트</h2>
        </div>
        <div class="fc-card">
          <span class="fc-badge fc-badge-warn">약점 가중</span>
          <h2 class="fc-h2" style="margin-top:8px">{{ weakestHomeName || '약점 요인' }} 보완 스트레칭</h2>
          <p class="fc-sub" style="margin-bottom:12px">{{ weakestHomeName }} 결과를 바탕으로 추천돼요.</p>
          <button class="fc-btn fc-btn-outline" @click="go('video')">DB 공식 운동 영상 보기</button>
        </div>
        <p class="fc-sub" style="margin-top:4px">측정하지 않은 요인이 있어도 기본 루틴의 유산소·근력 요소는 유지돼요.</p>
      </div>

      <!-- VIDEO -->
      <div class="fc-body" v-if="page==='video'">
        <button class="fc-nav-back" @click="go('recommend')">← 이전</button>
        <h1 class="fc-h1">국민체력100 운동 영상</h1>
        <span class="fc-badge fc-badge-good">AI Fitness DB · 국민체력100 공식 영상</span>
        <div class="fc-section-divider"></div>
        <p v-if="videoLoading" class="fc-sub">영상 DB를 불러오는 중입니다…</p><p v-if="videoError" class="fc-error">{{ videoError }}</p>
        <div class="fc-video-card" v-for="v in dbVideos" :key="v.url">
          <div class="fc-video-thumb">▶</div>
          <a class="fc-video-link" :href="'/video-player?url='+encodeURIComponent(v.url)+'&title='+encodeURIComponent(v.title)" target="_blank" rel="noopener"><div class="fc-video-title">{{ v.title }}</div><div class="fc-sub" style="margin:2px 0 0">{{ v.display_group }} · {{ v.age_group }} · {{ v.exercise_name }}</div></a>
        </div>
      </div>

    </div>

    <div class="fc-drawer-backdrop" v-if="videoSidebarOpen || chatSidebarOpen || guideSidebarOpen || measurementVideoSidebarOpen" @click="videoSidebarOpen=false;chatSidebarOpen=false;guideSidebarOpen=false;measurementVideoSidebarOpen=false"></div>
    <aside class="fc-drawer" v-if="guideSidebarOpen && selectedMeasureGuide" aria-label="측정 가이드 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-primary">HOME GUIDE</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedMeasureGuide.name }}</h2></div><button class="fc-drawer-close" @click="guideSidebarOpen=false" aria-label="닫기">×</button></div>
      <p class="fc-sub">{{ selectedMeasureGuide.why }}</p><dl class="fc-guide-copy"><dt>준비물</dt><dd>{{ selectedMeasureGuide.prep }}</dd><dt>필요한 공간</dt><dd>{{ selectedMeasureGuide.space }}</dd><dt>측정 방법</dt><dd>{{ selectedMeasureGuide.method }}</dd><dt>주의사항</dt><dd>{{ selectedMeasureGuide.caution }}</dd><template v-if="selectedMeasureGuide.note"><dt>측정 오차 핵심 기준</dt><dd>{{ selectedMeasureGuide.note }}</dd></template></dl>
    </aside>
    <aside class="fc-drawer" v-if="measurementVideoSidebarOpen && selectedMeasurementVideo" aria-label="측정 방법 동영상 가이드 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-good">MEASUREMENT VIDEO</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedMeasurementVideo.measurementName }}</h2></div><button class="fc-drawer-close" @click="measurementVideoSidebarOpen=false" aria-label="닫기">×</button></div>
      <p class="fc-sub">측정을 시작하기 전에 동작과 주의사항을 영상으로 확인해 보세요.</p>
      <measurement-video-player :key="selectedMeasurementVideo.youtubeId" :guide="selectedMeasurementVideo"></measurement-video-player>
      <p class="fc-measure-video-note">영상 시청 전후에도 측정 가이드의 준비물·공간·주의사항을 함께 확인해 주세요.</p>

    </aside>
    <aside class="fc-drawer" v-if="videoSidebarOpen" aria-label="운동 동영상 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-primary">DB 영상 TOP 3</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedVideoLabel }} 동영상 가이드</h2></div><button class="fc-drawer-close" @click="videoSidebarOpen=false" aria-label="닫기">×</button></div>
      <p v-if="videoLoading" class="fc-sub">영상 DB를 조회하는 중입니다…</p><p v-if="videoError" class="fc-error">{{ videoError }}</p>
      <div class="fc-drawer-video" v-for="(video,index) in dbVideos" :key="video.url"><strong>{{ index+1 }}. {{ video.title }}</strong><p class="fc-sub" style="margin:5px 0 0">{{ video.description || '국민체력100 공식 운동 영상' }}</p><video controls preload="metadata" :src="video.url"></video></div>
    </aside>

    <aside class="fc-drawer" v-if="chatSidebarOpen" aria-label="AI 체력 코치 챗봇 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-good">Qwen3 4B · E: 하네스</span><h2 class="fc-h2" style="margin:8px 0 0">AI 체력 코치 챗봇</h2></div><button class="fc-drawer-close" @click="chatSidebarOpen=false" aria-label="닫기">×</button></div>
      <div class="fc-chat-messages"><div v-for="(message,index) in chatMessages" :key="index" :class="['fc-chat-bubble',message.role]">{{ message.content }}</div><div v-if="chatLoading" class="fc-chat-bubble assistant">Qwen3가 DB 근거를 확인하고 있습니다…</div></div>
      <form class="fc-chat-form" @submit.prevent="sendChat"><input class="fc-input" v-model="chatInput" maxlength="500" autocomplete="off" placeholder="예: 내 유연성을 위한 운동을 알려줘"><button class="fc-btn fc-btn-primary" type="submit" :disabled="chatLoading || !chatInitialized || !chatInput.trim()">보내기</button></form>
    </aside>
  </div>
  `,
};

const app = createApp(App);
app.mount("#app");
