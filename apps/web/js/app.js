const { createApp, reactive, computed } = Vue;
const FitnessCoach = window.FitnessCoach;
if (!FitnessCoach) throw new Error('FitnessCoach dependencies must load before app.js');
const { ADULT_ITEMS, SENIOR_ITEMS, GRIP_ITEM, AGILITY_ITEM, CARDIO_ITEM, MEASUREMENT_RULES, HOME_BATTERY_CODES, CENTER_BATTERY_CODES } = FitnessCoach.measurementConfig;
const { RADAR_CONFIG, BACKEND_PERCENTILE_RANGE_WIDTH } = FitnessCoach.radarConfig;
const { MEASUREMENT_VIDEO_GUIDES, VIDEO_CATEGORY_BY_LABEL } = FitnessCoach.videoConfig;
const { MOCK_WORKOUT_RECOMMENDATIONS } = FitnessCoach.mockData;
const { isMeasurementValueValid, measurementItemsFor, buildPercentileMeasurements } = FitnessCoach.measurementUtils;
const { normalizeRadarValue, measuredRadarRuns, radarPoints: buildRadarPoints, radarIndexedPoints: buildRadarIndexedPoints, radarDotCoordinates: buildRadarDotCoordinates } = FitnessCoach.radarUtils;
const { extractYouTubeId } = FitnessCoach.youtubeUtils;
const { loadPercentiles: fetchPercentiles, loadReportSummary: fetchReportSummary, loadWorkoutVideos: fetchWorkoutVideos } = FitnessCoach.services;

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
    canEmbed() { return true; },
    embedUrl() {
      const params = new URLSearchParams({ autoplay: '1', controls: '1', rel: '0', playsinline: '1', enablejsapi: '1' });
      if (/^https?:$/.test(window.location.protocol)) params.set('origin', window.location.origin);
      return 'https://www.youtube-nocookie.com/embed/' + this.guide.youtubeId + '?' + params;
    },
  },
  created() { this._player = null; this._requestVersion = 0; this._disposed = false; this._readyTimer = null; },
  mounted() { this.attachPlayer(); },
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
      <div :key="attempt" class="fc-measure-video-frame">
        <iframe ref="frame" :src="embedUrl" :title="guide.title+' 측정 방법 영상'"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>
      </div>
      <p v-if="message" class="fc-measure-video-status" :class="{'is-error':status==='error'}" role="status" aria-live="polite">{{ message }}</p>
      <div class="fc-measure-video-actions">
        <button v-if="status==='error' && canEmbed" class="fc-measure-guide-btn" type="button" @click="retryPlayer">다시 시도</button>
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

const PROGRESS_MAP = { landing: null, login: null, basicInfo: 10, routeSelect: 20, parq: 30, homeGuide: 42, measureInput: 60, report: 82, recommend: 92, video: 100, centerInput: 60, centerGuidance: null };
const TITLE_MAP = { landing: "Landing", login: "Login", basicInfo: "기본정보", routeSelect: "측정 경로", parq: "PAR-Q", homeGuide: "홈 측정 가이드", measureInput: "결과 입력", report: "체력 리포트", recommend: "운동 추천", video: "운동 영상", centerInput: "센터 결과 입력", centerGuidance: "센터 안내" };

/* ============================================================
   VUE APP
   ============================================================ */

const App = {
  components: { MeasurementVideoPlayer },
  data() {
    return {
      page: "landing",
      form: { gender: "", age: "", height: "", weight: "" },
      authView: 'login',
      loginForm: { identifier: '', password: '' },
      signupForm: {
        identifier: '', password: '', passwordConfirm: '',
        gender: '', age: '', height: '', weight: ''
      },
      authNotice: '',
      route: null,
      parqAnswers: Array(7).fill(null),
      parqQuestionIndex: 0,
      parqBlocked: false,
      gripOwned: null,
      homeValues: {},
      centerValues: {},
      measurementView: "dashboard",
      activeMeasurementIndex: 0,
      openGuideIdx: 0,
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
    window.addEventListener('keydown',this.handleEscape);
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
  beforeUnmount() { window.removeEventListener('keydown',this.handleEscape); },
  computed: {
    ageGroup() { const age=Number(this.form.age); return age>=65?"senior":age>=19?"adult":"under19"; },
    under19Blocked() { const age=Number(this.form.age); return Number.isFinite(age) && age>0 && age<19; },
    battery() { return this.ageMeasurementItems.filter(item=>item.code!=='grip_strength'); },
    ageMeasurementItems() { return measurementItemsFor(this.ageGroup,'HOME',this.gripOwned); },
    homeMeasuredItems() { return measurementItemsFor(this.ageGroup,'HOME',this.gripOwned); },
    centerMeasuredItems() { return measurementItemsFor(this.ageGroup,'CENTER',this.gripOwned); },
    reportItems() { return this.route === "CENTER" ? this.centerMeasuredItems : this.homeMeasuredItems; },
    reportValues() { return this.route === "CENTER" ? this.centerValues : this.homeValues; },
    basicInfoValid() { const age=Number(this.form.age),height=Number(this.form.height),weight=Number(this.form.weight);return Boolean(this.form.gender)&&Number.isFinite(age)&&age>=19&&Number.isFinite(height)&&height>0&&Number.isFinite(weight)&&weight>0; },
    loginFormValid() {
      return Boolean(this.loginForm.identifier.trim() && this.loginForm.password);
    },
    signupPasswordMismatch() {
      return Boolean(this.signupForm.passwordConfirm) &&
        this.signupForm.password !== this.signupForm.passwordConfirm;
    },
    signupFormValid() {
      const age = Number(this.signupForm.age);
      const height = Number(this.signupForm.height);
      const weight = Number(this.signupForm.weight);
      return Boolean(
        this.signupForm.identifier.trim() &&
        this.signupForm.password &&
        this.signupForm.password === this.signupForm.passwordConfirm &&
        this.signupForm.gender &&
        Number.isFinite(age) && age > 0 &&
        Number.isFinite(height) && height > 0 &&
        Number.isFinite(weight) && weight > 0
      );
    },
    bmiValue() { const height=Number(this.form.height)/100,weight=Number(this.form.weight);return height>0&&weight>0?(weight/(height*height)).toFixed(1):''; },
    parqAnswered() { return this.parqAnswers.every(a => a !== null); },
    currentParqQuestion() { return this.parqQuestions[this.parqQuestionIndex] || ''; },
    answeredParqCount() { return this.parqAnswers.filter(answer => answer !== null).length; },
    activeMeasurementItem() { return this.homeMeasuredItems[this.activeMeasurementIndex] || this.homeMeasuredItems[0] || null; },
    completedMeasurementCount() { return this.battery.filter(item=>isMeasurementValueValid(item,this.homeValues[item.code])).length; },
    measurementTotalCount() { return this.battery.length; },
    homeInputAllFilled() { return this.gripOwned!==null && this.homeMeasuredItems.every(it => isMeasurementValueValid(it,this.homeValues[it.code])); },
    centerInputAllFilled() { return this.centerMeasuredItems.every(it => isMeasurementValueValid(it,this.centerValues[it.code])); },
    unmeasuredList() {
      if (this.route !== "HOME") return [];
      const notes = {
        "순발력": "HOME 측정으로 추정하지 않으며, 대응되는 센터 측정값이 있을 때 표시합니다.",
        "민첩성": "가까운 체력인증센터에서 측정할 수 있어요.",
        "악력": "악력계가 있을 때 상대악력으로 추가하거나 가까운 체력인증센터에서 측정할 수 있어요.",
        "심폐지구력": "가까운 체력인증센터에서 측정할 수 있어요.",
      };
      const list = this.radarAxes.filter(axis=>!axis.measured).map(axis=>({label:axis.label,note:notes[axis.label]||"현재 측정 경로에 포함되지 않은 항목입니다."}));
      if (this.ageGroup === 'senior') {
        const gripIndex=list.findIndex(item=>item.label==='악력');
        if(gripIndex>=0)list[gripIndex]={label:'악력(상지 근기능)',note:'악력계가 있을 때 상대악력으로 추가하거나 가까운 체력인증센터에서 측정할 수 있어요.'};
        list.push({label:'협응력',note:'어르신 HOME 배터리에 포함되지 않아 센터 측정 데이터가 필요합니다.'});
      }
      return list;
    },
    percentileRanked() {
      return this.radarAxes.filter(axis=>axis.compared&&Number.isFinite(Number(axis.topPercent))).map(axis=>({name:axis.label,pct:Number(axis.topPercent)})).sort((a,b)=>a.pct-b.pct);
    },
    strongest() { return this.percentileRanked[0]; },
    weakest() { return this.percentileRanked[this.percentileRanked.length - 1]; },
    comparisonRows() {
      return this.radarAxes.filter(axis=>axis.measured).map(axis=>{
        if(!axis.compared){const reference=axis.percentileEligible===false;return {code:axis.valueCode,name:axis.label,value:axis.raw,mode:reference?'reference':'pending',text:reference?'참고값 · 백분위 미제공':'또래 비교 준비 중',range:null};}
        const topPct=Number(axis.topPercent),width=BACKEND_PERCENTILE_RANGE_WIDTH[axis.valueCode];
        if(width!==undefined){const range=[Math.max(1,Math.round(topPct-width)),Math.min(99,Math.round(topPct+width))];return {code:axis.valueCode,name:axis.label,value:axis.raw,mode:'range',text:`또래 상위 ${range[0]}~${range[1]}%`,range};}
        return {code:axis.valueCode,name:axis.label,value:axis.raw,mode:'point',text:`또래 상위 ${Math.round(topPct)}%`,range:[topPct,topPct]};
      });
    },
    measuredReportCount() { return this.radarAxes.filter(axis=>axis.measured).length; },
    radarAxes() {
      const resultByCode = Object.fromEntries(this.percentileResults.map(item => [item.code, item]));
      const values = this.reportValues;
      const grip = Number(values.grip_strength);
      const weight = Number(this.form.weight || 0);
      const gripRelative = Number.isFinite(grip) && grip >= 0 && weight > 0 ? grip / weight * 100 : null;
      const configs = RADAR_CONFIG[this.ageGroup] || RADAR_CONFIG.adult;
      return configs.map(axis => {
        const row = resultByCode[axis.code];
        const hasRawValue=values[axis.valueCode]!==undefined&&values[axis.valueCode]!==''&&Number.isFinite(Number(values[axis.valueCode]));
        const measured = axis.code === 'GRIP_RELATIVE' ? this.gripOwned===true&&hasRawValue : hasRawValue;
        const rawValue = axis.code === 'GRIP_RELATIVE' ? gripRelative : Number(values[axis.valueCode]);
        const radarDisplayValue = measured ? normalizeRadarValue(rawValue,axis.min,axis.max,axis.lowerBetter) : null;
        const raw = axis.code === 'GRIP_RELATIVE' ? (measured ? `${grip}kg · 상대악력 ${gripRelative.toFixed(1)}%` : '미측정') : (measured ? `${values[axis.valueCode]}${axis.unit}` : '미측정');
        const chartRaw=axis.code==='GRIP_RELATIVE'?(measured?`${gripRelative.toFixed(1)}%`:'미측정'):(measured?`${values[axis.valueCode]}${axis.unit}`:'미측정');
        const hasAverageData=Boolean(row?.available && row?.average_value!==null && row?.average_value!==undefined);
        const chartAverage=hasAverageData?`${Number(row.average_value).toFixed(1)}${axis.code==='GRIP_RELATIVE'?'%':axis.unit}`:'';
        const averageRadarDisplayValue=hasAverageData?normalizeRadarValue(Number(row.average_value),axis.min,axis.max,axis.lowerBetter):null;
        const compared=Boolean(measured&&row?.available&&axis.percentileEligible!==false);
        return {...axis, raw, chartRaw, chartAverage, measured, radarDisplayValue, topPercent:compared?row.top_percent:null, averageRadarDisplayValue, averageValue:row?.average_value, hasAverageData, comparisonBand:row?.age_band, exactAgeMatch:row?.exact_age_match!==false, compared};
      });
    },
    hasAverageData() { return this.radarAxes.some(axis => axis.hasAverageData); },
    radarAccessibleDescription() {
      return this.radarAxes.map(axis => {
        const reference = this.ageGroup === 'senior' && axis.valueCode === 'chair_sit_and_reach_3m'
          ? ', 참고값, 백분위 미제공'
          : '';
        return `${axis.label} ${axis.measured ? axis.raw : '미측정'}${reference}`;
      }).join('; ');
    },
    radarUserPolygonPoints() { const values=this.radarAxes.map(axis=>axis.radarDisplayValue);return values.length&&values.every(Number.isFinite)?this.radarPoints(values):''; },
    radarUserSegments() { const values=this.radarAxes.map(axis=>axis.radarDisplayValue);return measuredRadarRuns(values).map(run=>this.radarIndexedPoints(values,run)); },
    radarAveragePolygonPoints() { const values=this.radarAxes.map(axis=>axis.averageRadarDisplayValue);return values.length&&values.every(Number.isFinite)?this.radarPoints(values):''; },
    radarAverageSegments() { const values=this.radarAxes.map(axis=>axis.averageRadarDisplayValue);return measuredRadarRuns(values).map(run=>this.radarIndexedPoints(values,run)); },
    radarGridLevels() { return [100,80,60,40,20].map(level=>({level,points:this.radarPoints(this.radarAxes.map(()=>level))})); },
    radarUserDots() { return this.radarDotCoordinates(this.radarAxes.map(axis=>axis.radarDisplayValue)); },
    radarAverageDots() { return this.radarDotCoordinates(this.radarAxes.map(axis=>axis.averageRadarDisplayValue)); },
    radarOuterPoints() { return this.radarPoints(this.radarAxes.map(()=>100)); },
    radarInnerPoints() { return this.radarPoints(this.radarAxes.map(()=>50)); },
    radarLabelPoints() {
      const count=this.radarAxes.length,center=150,radius=125;
      return this.radarAxes.map((axis,index)=>{const angle=-Math.PI/2+index*2*Math.PI/count;const x=center+Math.cos(angle)*radius;return {...axis,x,y:center+Math.sin(angle)*radius+4,axisX:center+Math.cos(angle)*94,axisY:center+Math.sin(angle)*94,anchor:x<center-10?'start':x>center+10?'end':'middle'}});
    },
    weakestHomeName() {
      return this.weakest?.name || '';
    },
    recommendedWorkouts() {
      const base=MOCK_WORKOUT_RECOMMENDATIONS.base.map(item=>({...item,opensVideo:false}));
      const focus=this.weakestHomeName||'전신 체력';
      return [...base,{...MOCK_WORKOUT_RECOMMENDATIONS.weakness,title:`${focus} ${MOCK_WORKOUT_RECOMMENDATIONS.weakness.titleSuffix}`}];
    },
    recommendedWorkoutMinutes() { return this.recommendedWorkouts.reduce((total,item)=>total+Number(item.durationMinutes||0),0); },
    progressLabel() { return TITLE_MAP[this.page]; },
    progressPctBar() { return PROGRESS_MAP[this.page]; },
  },
  methods: {
    go(next) { this.page = next; window.scrollTo(0, 0); },
    showAuthUnavailable(kind) {
      if (kind === 'signup' && this.signupForm.password !== this.signupForm.passwordConfirm) {
        this.authNotice = '비밀번호가 일치하지 않습니다.';
        return;
      }
      this.authNotice = '현재 인증 서버가 연결되지 않아 이 기능을 사용할 수 없습니다.';
    },
    continueAsGuest() {
      this.authNotice = '';
      this.go('basicInfo');
    },
    handleEscape(event) {
      if(event.key!=='Escape')return;
      if(this.chatSidebarOpen){this.closeChat();return;}
      this.videoSidebarOpen=false;this.guideSidebarOpen=false;this.measurementVideoSidebarOpen=false;
    },
    toggleGuide(i) { this.openGuideIdx = this.openGuideIdx === i ? -1 : i; },
    measurementVideoFor(item){
      return MEASUREMENT_VIDEO_GUIDES[`senior_${item.code}`] || MEASUREMENT_VIDEO_GUIDES[item.code] || null;
    },
    youtubeGuideFor(video) {
      const youtubeId=extractYouTubeId(video?.youtubeId||video?.youtube_id||video?.youtube_url||video?.url||'');
      return youtubeId?{title:video?.title||video?.exercise_name||'국민체력100 운동 영상',youtubeId}:null;
    },
    measurementMin(item) { return MEASUREMENT_RULES[item.code]?.min ?? 0; },
    measurementValueValid(item,value) { return isMeasurementValueValid(item,value); },
    showMeasureGuide(item){this.selectedMeasureGuide=item;this.guideSidebarOpen=true;this.measurementVideoSidebarOpen=false;this.videoSidebarOpen=false;this.chatSidebarOpen=false;},
    showMeasurementVideo(item) {
      const video = this.measurementVideoFor(item);
      if (!video) return;
      this.selectedMeasurementVideo = { ...video, measurementName: item.name };
      this.measurementVideoSidebarOpen = true;
      if ('guideSidebarOpen' in this) this.guideSidebarOpen = false;
      if ('videoSidebarOpen' in this) this.videoSidebarOpen = false;
      if ('chatSidebarOpen' in this) this.chatSidebarOpen = false;
    },
    setParq(i, val) { this.parqAnswers[i] = val; },
    answerCurrentParq(val) {
      this.setParq(this.parqQuestionIndex,val);
      if(this.parqQuestionIndex<this.parqQuestions.length-1)this.parqQuestionIndex+=1;
    },
    showPreviousParq() { if(this.parqQuestionIndex>0)this.parqQuestionIndex-=1; },
    measurementState(item) {
      if(isMeasurementValueValid(item,this.homeValues[item.code]))return '완료';
      return this.activeMeasurementItem?.code===item.code&&this.measurementView==='active'?'측정 중':'대기';
    },
    selectMeasurement(item) {
      const index=this.homeMeasuredItems.findIndex(candidate=>candidate.code===item.code);
      if(index<0)return;
      this.activeMeasurementIndex=index;
      this.measurementView='active';
      window.scrollTo(0,0);
    },
    clearActiveMeasurement() {
      if(this.activeMeasurementItem)this.homeValues[this.activeMeasurementItem.code]='';
    },
    completeActiveMeasurement() {
      const item=this.activeMeasurementItem;
      if(!item||!isMeasurementValueValid(item,this.homeValues[item.code]))return;
      const nextIndex=this.homeMeasuredItems.findIndex(candidate=>!isMeasurementValueValid(candidate,this.homeValues[candidate.code]));
      if(nextIndex>=0){this.activeMeasurementIndex=nextIndex;this.measurementView='active';window.scrollTo(0,0);return;}
      if(this.gripOwned!==null)this.openReport();
    },
    submitParq() {
      this.route = "HOME";
      if (this.parqAnswers.some(a => a === true)) { this.parqBlocked = true; this.go("centerGuidance"); }
      else { this.parqBlocked = false; this.go("measureInput"); }
    },
    startCenterRoute() { this.route = "CENTER"; this.go("centerInput"); },
    radarPoints(values) {
      return buildRadarPoints(values);
    },
    radarPointsAtIndices(values) {
      return buildRadarIndexedPoints(values,values.map((value,index)=>Number.isFinite(value)?index:null).filter(index=>index!==null));
    },
    radarIndexedPoints(values,indices) {
      return buildRadarIndexedPoints(values,indices);
    },
    radarDotCoordinates(values) {
      return buildRadarDotCoordinates(values);
    },
    async loadPercentiles() {
      this.chartLoading=true;this.chartError="";
      const values=this.reportValues;
      const measurements=buildPercentileMeasurements(RADAR_CONFIG[this.ageGroup]||RADAR_CONFIG.adult,values,Number(this.form.weight),this.gripOwned);
      try {
        const data=await fetchPercentiles({age:Number(this.form.age),sex:this.form.gender==='여성'?'F':'M',measurements});
        this.percentileResults=data.results||[];this.normPeriodNote=data.result_label;
      } catch(error) { this.chartError="";this.percentileResults=[]; }
      finally { this.chartLoading=false; }
    },
    async loadReportSummary(){
      this.reportSummaryLoading=true;this.reportSummary='';
      const results=this.radarAxes.map(axis=>({label:axis.label,input:axis.raw,top_percent:axis.topPercent,average:axis.averageValue,age_band:axis.comparisonBand,compared:axis.compared}));
      try{const data=await fetchReportSummary({age:Number(this.form.age),sex:this.form.gender,results});this.reportSummary=data.summary||'';}catch(error){this.reportSummary='측정 결과 설명을 불러오지 못했습니다.';}finally{this.reportSummaryLoading=false;}
    },
    async openReport(){this.go('report');await this.loadPercentiles();this.loadReportSummary();},
    async loadWorkoutVideos(category='endurance'){
      this.dbVideos=[];this.videoLoading=true;this.videoError="";
      try{
        const data=await fetchWorkoutVideos(category);
        this.dbVideos=Array.isArray(data.videos)?data.videos:[];
      }catch(error){
        this.videoError='운동 영상을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.';
      }finally{this.videoLoading=false}
    },
    openVideoLibrary(){const category=VIDEO_CATEGORY_BY_LABEL[this.weakestHomeName]||'endurance';this.go('video');this.loadWorkoutVideos(category);},
    async showAxisVideos(category,label){
      this.selectedVideoAxis=category;this.selectedVideoLabel=label;this.videoSidebarOpen=true;this.guideSidebarOpen=false;this.measurementVideoSidebarOpen=false;this.chatSidebarOpen=false;this.dbVideos=[];this.videoLoading=true;this.videoError="";
      await this.loadWorkoutVideos(category);
    },
    async openChat(){
      this.videoSidebarOpen=false;this.guideSidebarOpen=false;this.measurementVideoSidebarOpen=false;this.chatSidebarOpen=true;
      await this.$nextTick();
      this.$refs.chatInput?.focus();
      if(this.chatInitialized||this.chatLoading)return;
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
    closeChat(){
      this.chatSidebarOpen=false;
      this.$nextTick(()=>this.$refs.chatTrigger?.focus());
    },
    handleChatDialogKeydown(event){
      if(event.key==='Escape'){event.preventDefault();this.closeChat();return;}
      if(event.key!=='Tab')return;
      const controls=[...event.currentTarget.querySelectorAll('button:not([disabled]),input:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])')];
      if(!controls.length)return;
      const first=controls[0];const last=controls[controls.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
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
  },
  template: `
  <div class="fc-root">
    <div class="fc-phone">
      <div class="fc-topbar">
        <button class="fc-brand" type="button" @click="go('landing')" aria-label="홈 화면으로 이동"><span class="fc-brand-mark"></span>체력코치 AI</button>
        <div style="display:flex;gap:8px;align-items:center"><span :class="['fc-badge', apiStatus==='ok' ? 'fc-badge-good' : 'fc-badge-warn']">{{ apiStatusText }}</span><span class="fc-step-label">{{ progressLabel }}</span></div>
      </div>
      <div class="fc-progress-track" v-if="progressPctBar !== null">
        <div class="fc-progress-fill" :style="{ width: progressPctBar + '%' }"></div>
      </div>

      <!-- LANDING -->
      <div class="fc-body fc-landing" style="display:flex;flex-direction:column;justify-content:center;min-height:640px" v-if="page==='landing'">
        <p class="fc-eyebrow">체력코치 AI</p>
        <h1 class="fc-hero-title">내 체력을 직접 확인하고<br/>다음 운동까지 이어가세요.</h1>
        <p class="fc-hero-copy">약 10~15분이면 자가측정을 시작할 수 있어요.</p>
        <div class="fc-landing-visual">
          <img src="./assets/fitness-coach-landing.png" alt="체육관에서 여러 체력 측정 종목에 참여하는 체력코치 캐릭터">
        </div>
        <ul class="fc-value-list" aria-label="서비스 특징">
          <li>자가측정 가능</li>
          <li>국민체력100 데이터 기반</li>
        </ul>
        <button class="fc-btn fc-btn-primary" @click="go('login')">체력 측정 시작</button>
        <p class="fc-secondary-prompt">이미 센터에서 측정했다면 로그인 후 센터 결과를 입력할 수 있어요.</p>
      </div>

      <!-- LOGIN -->
      <div class="fc-body fc-page-login" v-if="page==='login'">
        <button class="fc-nav-back" @click="go('landing')">← 이전</button>
        <h1 class="fc-eyebrow">체력코치 AI</h1>
        <h2 class="fc-h1">{{ authView === 'login' ? '로그인' : '회원가입' }}</h2>
        <p class="fc-sub">인증 서버 연결 전에도 비로그인으로 체력 측정을 시작할 수 있어요.</p>
        <div class="fc-auth-switch" role="group" aria-label="인증 화면 선택">
          <button type="button" :class="['fc-segment-button', authView==='login' ? 'active':'']" :aria-pressed="authView==='login'" @click="authView='login';authNotice=''">로그인</button>
          <button type="button" :class="['fc-segment-button', authView==='signup' ? 'active':'']" :aria-pressed="authView==='signup'" @click="authView='signup';authNotice=''">회원가입</button>
        </div>
        <form v-if="authView==='login'" class="fc-auth-panel" @submit.prevent="showAuthUnavailable('login')">
          <div class="fc-field"><label class="fc-label" for="login-identifier">아이디</label><input id="login-identifier" class="fc-input" v-model="loginForm.identifier" autocomplete="username" /></div>
          <div class="fc-field"><label class="fc-label" for="login-password">비밀번호</label><input id="login-password" class="fc-input" type="password" v-model="loginForm.password" autocomplete="current-password" /></div>
          <button class="fc-btn fc-btn-primary" type="submit" :disabled="!loginFormValid">로그인</button>
        </form>
        <form v-else class="fc-auth-panel" @submit.prevent="showAuthUnavailable('signup')">
          <div class="fc-field"><label class="fc-label" for="signup-identifier">아이디 또는 이메일</label><input id="signup-identifier" class="fc-input" v-model="signupForm.identifier" autocomplete="username" /></div>
          <div class="fc-field"><label class="fc-label" for="signup-password">비밀번호</label><input id="signup-password" class="fc-input" type="password" v-model="signupForm.password" autocomplete="new-password" /></div>
          <div class="fc-field"><label class="fc-label" for="signup-password-confirm">비밀번호 확인</label><input id="signup-password-confirm" class="fc-input" type="password" v-model="signupForm.passwordConfirm" autocomplete="new-password" /></div>
          <p v-if="signupPasswordMismatch" class="fc-auth-notice" role="status">비밀번호가 일치하지 않습니다.</p>
          <div class="fc-signup-profile">
            <div class="fc-field"><span class="fc-label" id="signup-gender-label">성별</span><div class="fc-select-grid" role="group" aria-labelledby="signup-gender-label"><button type="button" :class="['fc-segment-button', signupForm.gender==='여성' ? 'active':'']" :aria-pressed="signupForm.gender==='여성'" @click="signupForm.gender='여성'">여성</button><button type="button" :class="['fc-segment-button', signupForm.gender==='남성' ? 'active':'']" :aria-pressed="signupForm.gender==='남성'" @click="signupForm.gender='남성'">남성</button></div></div>
            <div class="fc-field"><label class="fc-label" for="signup-age">나이</label><input id="signup-age" class="fc-input" type="number" inputmode="numeric" v-model="signupForm.age" /></div>
            <div class="fc-field"><label class="fc-label" for="signup-height">키</label><input id="signup-height" class="fc-input" type="number" inputmode="decimal" step="0.1" v-model="signupForm.height" /></div>
            <div class="fc-field"><label class="fc-label" for="signup-weight">체중</label><input id="signup-weight" class="fc-input" type="number" inputmode="decimal" step="0.1" v-model="signupForm.weight" /></div>
          </div>
          <button class="fc-btn fc-btn-primary" type="submit" :disabled="!signupFormValid">회원가입</button>
        </form>
        <p v-if="authNotice && !signupPasswordMismatch" class="fc-auth-notice" role="status">{{ authNotice }}</p>
        <div class="fc-auth-divider" aria-hidden="true"><span>또는</span></div>
        <button class="fc-btn fc-btn-outline" type="button" @click="continueAsGuest">비로그인으로 이용하기</button>
      </div>

      <!-- BASIC INFO -->
      <div class="fc-body fc-page-basic" v-if="page==='basicInfo'">
        <button class="fc-nav-back" @click="go('login')">← 이전</button>
        <p class="fc-eyebrow">1단계 · 기본 정보</p>
        <h1 class="fc-h1">측정에 필요한 정보만 알려주세요</h1>
        <p class="fc-sub">연령에 맞는 측정 항목을 구성하고 기록을 해석할 때 사용합니다.</p>
        <div class="fc-form-card">
          <div class="fc-field">
          <span class="fc-label" id="basic-gender-label">성별</span>
          <div class="fc-select-grid">
            <button type="button" :class="['fc-segment-button', form.gender==='여성' ? 'active':'']" :aria-pressed="form.gender==='여성'" aria-describedby="basic-gender-label" @click="form.gender='여성'">여성</button>
            <button type="button" :class="['fc-segment-button', form.gender==='남성' ? 'active':'']" :aria-pressed="form.gender==='남성'" aria-describedby="basic-gender-label" @click="form.gender='남성'">남성</button>
          </div>
        </div>
          <div class="fc-field"><label class="fc-label" for="basic-age">만 나이</label><div class="fc-input-row"><input id="basic-age" class="fc-input" type="number" inputmode="numeric" placeholder="예: 34" v-model="form.age" /><span class="fc-unit">세</span></div></div>
          <div class="fc-field"><label class="fc-label" for="basic-height">키</label><div class="fc-input-row"><input id="basic-height" class="fc-input" type="number" inputmode="decimal" step="0.1" placeholder="170.0" v-model="form.height" /><span class="fc-unit">cm</span></div></div>
          <div class="fc-field"><label class="fc-label" for="basic-weight">체중</label><div class="fc-input-row"><input id="basic-weight" class="fc-input" type="number" inputmode="decimal" step="0.1" placeholder="65.0" v-model="form.weight" /><span class="fc-unit">kg</span></div></div>
          <div class="fc-bmi-context" v-if="bmiValue"><span>BMI</span><strong>{{ bmiValue }}</strong><small>신장과 체중으로 계산한 참고값</small></div>
        </div>
        <div class="fc-card-soft" v-if="under19Blocked"><span class="fc-badge fc-badge-blocked">연령 기준 확인 필요</span><p class="fc-sub" style="margin:8px 0 0">만 19세 미만 측정 배터리는 현재 확정되지 않아 이 버전에서는 진행할 수 없습니다.</p></div>
        <div class="fc-sticky-action"><button class="fc-btn fc-btn-primary" :disabled="!basicInfoValid" @click="go('routeSelect')">다음</button></div>
      </div>

      <!-- ROUTE SELECT -->
      <div class="fc-body fc-page-route" v-if="page==='routeSelect'">
        <button class="fc-nav-back" @click="go('basicInfo')">← 이전</button>
        <p class="fc-eyebrow">측정 방법</p>
        <h1 class="fc-h1">어떻게 측정하시겠어요?</h1>
        <p class="fc-sub">내 상황에 맞는 방법을 선택하세요. 두 경로 모두 같은 체력 리포트로 이어집니다.</p>
        <button type="button" class="fc-route-card" @click="go('parq')">
          <span class="fc-route-card-icon" aria-hidden="true">⌂</span>
          <span class="fc-route-card-copy"><strong>직접 측정하기</strong><small>집이나 운동공간에서 안전 문진 후 측정합니다.</small></span>
          <span class="fc-route-card-tag">HOME</span>
        </button>
        <button type="button" class="fc-route-card" @click="startCenterRoute">
          <span class="fc-route-card-icon" aria-hidden="true">▦</span>
          <span class="fc-route-card-copy"><strong>센터 결과 입력</strong><small>국민체력100 센터에서 받은 기록을 그대로 입력합니다.</small></span>
          <span class="fc-route-card-tag">CENTER</span>
        </button>
      </div>

      <!-- PAR-Q -->
      <div class="fc-body fc-page-parq" v-if="page==='parq'">
        <button class="fc-nav-back" @click="go('routeSelect')">← 이전</button>
        <p class="fc-eyebrow">2단계 · 안전 확인</p>
        <h1 class="fc-h1" id="parq-heading">운동 전 안전 확인</h1>
        <p class="fc-sub">아래 7개 문항에 모두 답해주세요. 하나라도 ‘예’이면 안전을 위해 센터 측정을 안내합니다.</p>
        <section class="fc-parq-list" aria-labelledby="parq-heading">
          <article class="fc-parq-item" v-for="(question,index) in parqQuestions" :key="index">
            <h2 :id="'parq-question-'+index"><span>{{ index + 1 }}</span>{{ question }}</h2>
            <div class="fc-yn" role="group" :aria-labelledby="'parq-question-'+index">
              <button type="button" :class="['no',parqAnswers[index]===false?'active':'']"
                :aria-pressed="parqAnswers[index]===false" @click="setParq(index,false)">아니오</button>
              <button type="button" :class="['yes',parqAnswers[index]===true?'active':'']"
                :aria-pressed="parqAnswers[index]===true" @click="setParq(index,true)">예</button>
            </div>
          </article>
        </section>
        <div class="fc-sticky-action">
          <button class="fc-btn fc-btn-primary" :disabled="!parqAnswered" @click="submitParq">확인하고 다음</button>
        </div>
      </div>

      <!-- HOME GUIDE -->
      <div class="fc-body fc-page-home-guide" v-if="page==='homeGuide'">
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
      <div class="fc-body fc-page-measure" v-if="page==='measureInput'">
        <button class="fc-nav-back" @click="go('parq')">← 이전</button>
        <p class="fc-eyebrow">3단계 · 자가측정</p>
        <h1 class="fc-h1">측정 결과를 입력해 주세요</h1>
        <p class="fc-sub">각 종목의 측정값을 입력하면 바로 체력 리포트를 확인할 수 있어요.</p>
        <div class="fc-measure-grid">
          <article class="fc-measure-card" v-for="(it,i) in homeMeasuredItems" :key="it.code">
            <div class="fc-measure-card-head"><span>{{ i + 1 }}</span><h2>{{ it.name }}</h2></div>
            <label class="fc-label" :for="'measure-'+it.code">측정값</label>
            <div class="fc-raw-input"><input :id="'measure-'+it.code" type="number" step="any" inputmode="decimal" :min="measurementMin(it)" placeholder="0" v-model="homeValues[it.code]" /><span>{{ it.unit }}</span></div>
            <p class="fc-measure-note" v-if="it.note">{{ it.note }}</p>
            <div class="fc-input-actions"><button type="button" class="fc-measure-guide-btn" @click="showMeasureGuide(it)">측정 방법</button><button v-if="measurementVideoFor(it)" type="button" class="fc-measure-video-btn" @click="showMeasurementVideo(it)">▶ 영상 보기</button></div>
          </article>
        </div>
        <section class="fc-grip-option">
          <div><strong>악력 측정 추가</strong><p>악력계를 사용해 측정할지 반드시 선택해 주세요.</p></div>
          <div class="fc-select-grid"><button type="button" :class="['fc-segment-button',gripOwned===true?'active':'']" :aria-pressed="gripOwned===true" @click="gripOwned=true">악력계 있어요</button><button type="button" :class="['fc-segment-button',gripOwned===false?'active':'']" :aria-pressed="gripOwned===false" @click="gripOwned=false">측정하지 않아요</button></div>
        </section>
        <div class="fc-sticky-action"><button class="fc-btn fc-btn-primary" :disabled="!homeInputAllFilled" @click="openReport">측정 완료 · 리포트 보기</button></div>
      </div>

      <!-- CENTER INPUT -->
      <div class="fc-body fc-page-center-input" v-if="page==='centerInput'">
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
            <input class="fc-input" type="number" step="any" :min="measurementMin(it)" placeholder="0" v-model="centerValues[it.code]" />
            <span class="fc-unit">{{ it.unit }}</span>
          </div>
        </div>
        <button class="fc-btn fc-btn-primary" :disabled="gripOwned===null || !centerInputAllFilled" @click="openReport">리포트 보기</button>
      </div>

      <!-- CENTER GUIDANCE -->
      <div class="fc-body fc-page-center-guidance" v-if="page==='centerGuidance'">
        <h1 class="fc-h1">체력인증센터 안내</h1>
        <div class="fc-card-soft" v-if="parqBlocked">
          <span class="fc-badge fc-badge-blocked">PAR-Q 1개 이상 '예'</span>
          <p class="fc-sub" style="margin:10px 0 8px">응답해주신 내용상 혼자 체력측정을 진행하기보다<br>체력인증센터에서 전문가와 함께 측정하는 것을 권장합니다.</p>
          <p class="fc-sub" style="margin:0">전국 체력인증센터에서 체력측정과 상담을 받을 수 있습니다.</p>
        </div>
        <div class="fc-card fc-radar-card">
          <h2 class="fc-h2">지금 이용 가능해요</h2>
          <button class="fc-btn fc-btn-outline" style="margin-bottom:8px" @click="go('centerInput')">센터 측정 결과 입력</button>
          <button class="fc-btn fc-btn-outline" style="margin-bottom:8px" @click="openVideoLibrary">공단 운동 영상 열람</button>
          <a class="fc-btn fc-btn-outline" href="https://nfa.kspo.or.kr/intro/centerList.kspo"
            target="_blank" rel="noopener" aria-label="가까운 체력인증센터 찾기, 새 창">
            가까운 체력인증센터 찾기
          </a>
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
      <div class="fc-body fc-page-report" v-if="page==='report'">
        <header class="fc-report-hero">
          <p class="fc-eyebrow">4단계 · 결과 이해</p>
          <h1 class="fc-h1">나의 체력 리포트</h1>
          <div class="fc-report-completion"><strong>{{ route==='HOME' ? '자가측정' : '센터측정' }}</strong><span>{{ measuredReportCount }}개 항목 확인</span></div>
          <p class="fc-report-summary">{{ reportSummaryLoading ? '측정 결과를 간단히 정리하고 있습니다…' : reportSummary }}</p>
          <span class="fc-badge fc-badge-mock">{{ normPeriodNote }}</span>
        </header>

        <section class="fc-report-section fc-report-radar-section">
          <div class="fc-section-heading"><div><p class="fc-eyebrow">체력 프로필</p><h2 class="fc-h2">측정 기록의 형태</h2></div><span>점수가 아닌 원값 위치</span></div>
          <p class="fc-sub">파란색은 입력한 측정 기록의 위치예요. 축마다 표시 범위가 다르며 체력점수나 백분위가 아닙니다.</p>
          <div class="fc-card fc-radar-card">
          <div v-if="chartLoading" class="fc-sub">측정 DB와 비교하는 중입니다…</div>
          <div v-else>
            <svg class="fc-radar" viewBox="0 0 300 300" role="img" :aria-label="'체력 프로필 레이더 차트. '+radarAccessibleDescription">
              <defs><linearGradient id="userGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#A8D9FF" stop-opacity=".82"/><stop offset="100%" stop-color="#6FB8F6" stop-opacity=".72"/></linearGradient><linearGradient id="averageGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#FFD3A8" stop-opacity=".82"/><stop offset="100%" stop-color="#FFB66E" stop-opacity=".72"/></linearGradient><filter id="softShadow" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#0B4EA2" flood-opacity=".13"/></filter></defs>
              <polygon v-for="grid in radarGridLevels" :key="grid.level" :class="['fc-radar-grid','level-'+grid.level]" :points="grid.points"/>
              <line v-for="point in radarLabelPoints" :key="'line-'+point.code" class="fc-radar-axis" x1="150" y1="150" :x2="point.axisX" :y2="point.axisY"/>
              <polygon v-if="radarAveragePolygonPoints" class="fc-radar-average" :points="radarAveragePolygonPoints"/><polyline v-for="(segment,index) in radarAverageSegments" :key="'avg-segment-'+index" class="fc-radar-average-segment" :points="segment"/><polygon v-if="radarUserPolygonPoints" class="fc-radar-user" :points="radarUserPolygonPoints"/><polyline v-for="(segment,index) in radarUserSegments" :key="'user-segment-'+index" class="fc-radar-user-segment" :points="segment"/>
              <template v-if="hasAverageData"><circle v-for="(dot,index) in radarAverageDots" :key="'avg-dot-'+index" class="fc-radar-dot-average" :cx="dot.x" :cy="dot.y" r="3.5"/></template><circle v-for="(dot,index) in radarUserDots" :key="'user-dot-'+index" class="fc-radar-dot-user" :cx="dot.x" :cy="dot.y" r="4"/>
              <circle class="fc-radar-center" cx="150" cy="150" r="3"/>
              <text v-for="point in radarLabelPoints" :key="'label-'+point.code" class="fc-radar-label" :x="point.x" :y="point.y" :text-anchor="point.anchor">{{ point.label }}</text>
              <text v-for="point in radarLabelPoints" :key="'value-'+point.code" class="fc-radar-axis-value" :class="{'is-unmeasured':!point.measured}" :x="point.x" :y="point.y+13" :text-anchor="point.anchor">{{ point.measured ? point.chartRaw : '미측정' }}</text>
              <text v-for="point in radarLabelPoints.filter(item=>item.hasAverageData)" :key="'average-'+point.code" class="fc-radar-axis-average" :x="point.x" :y="point.y+24" :text-anchor="point.anchor">또래 평균 {{ point.chartAverage }}</text>
            </svg>
            <div class="fc-radar-legend"><span><i class="fc-radar-key fc-radar-key-user"></i>나의 측정값</span><span v-if="hasAverageData"><i class="fc-radar-key fc-radar-key-average"></i>또래 평균</span></div>
          </div>
          <p v-if="chartError" class="fc-error">{{ chartError }}</p>
        </div>
        </section>

        <section class="fc-report-section fc-report-compare-section">
          <div class="fc-section-heading"><div><p class="fc-eyebrow">또래 비교</p><h2 class="fc-h2">Backend 규준 결과</h2></div></div>
          <div class="fc-compare-list">
            <article v-for="row in comparisonRows" :key="'compare-'+row.code" class="fc-compare-row">
              <span>{{ row.name }}</span><strong :class="'is-'+row.mode">{{ row.text }}</strong>
            </article>
          </div>
        </section>

        <section class="fc-report-section fc-report-unmeasured-section" v-if="unmeasuredList.length">
          <div class="fc-section-heading"><div><p class="fc-eyebrow">다음 확인</p><h2 class="fc-h2">아직 확인하지 않은 체력</h2></div></div>
          <div class="fc-signal-list"><div class="fc-signal-row fc-unmeasured-card" v-for="u in unmeasuredList" :key="u.label"><span><strong>{{ u.label }}</strong><small>{{ u.note }}</small></span></div></div>
        </section>

        <section class="fc-report-section fc-report-action-section">
          <p class="fc-eyebrow">다음 행동</p><h2 class="fc-h2">오늘 바로 시작할 운동</h2>
          <p class="fc-sub">현재 단계에서는 Mock 운동 구성과 국민체력100 운동 영상을 제공합니다.</p>
          <button class="fc-btn fc-btn-primary" @click="go('recommend')">나의 운동 추천</button>
        </section>

        <section class="fc-report-section fc-report-center-section">
          <p class="fc-eyebrow">더 정확한 확인</p><h2 class="fc-h2">센터 측정 안내</h2>
          <a class="fc-btn fc-btn-outline" href="https://nfa.kspo.or.kr/intro/centerList.kspo"
            target="_blank" rel="noopener" aria-label="가까운 체력인증센터 찾기, 새 창">
            가까운 체력인증센터 찾기
          </a>
        </section>

        <footer class="fc-report-footer-note">
          본 리포트는 자가측정 기반 참고 정보이며,<br>
          국민체력100 공식 인증 결과가 아닙니다.<br>
          의학적 진단을 대체하지 않습니다.
        </footer>
      </div>

      <!-- RECOMMEND -->
      <div class="fc-body fc-page-recommend" v-if="page==='recommend'">
        <button class="fc-nav-back" @click="go('report')">← 이전</button>
        <p class="fc-eyebrow">5단계 · 다음 운동</p>
        <h1 class="fc-h1">오늘의 운동</h1>
        <span class="fc-badge fc-badge-mock">MOCK 운동 처방 · DB 영상 연결</span>
        <div class="fc-routine-summary"><strong>총 약 {{ recommendedWorkoutMinutes }}분</strong><span>{{ recommendedWorkouts.length }}개 운동</span></div>
        <div class="fc-routine-list">
          <article class="fc-routine-card" v-for="(item,index) in recommendedWorkouts" :key="item.title">
            <span class="fc-routine-step">{{ String(index+1).padStart(2,'0') }}</span>
            <div class="fc-routine-copy"><span :class="['fc-badge',item.tone==='warn'?'fc-badge-warn':'fc-badge-primary']">{{ item.phase || item.badge }}</span><h2>{{ item.title }}</h2><p>{{ item.durationMinutes }}분 · {{ item.opensVideo ? (weakestHomeName ? weakestHomeName+' Backend 비교 결과 기반 Mock' : '기본 전신 체력 Mock') : '기본 루틴' }}</p></div>
            <button v-if="item.opensVideo" class="fc-routine-video" @click="openVideoLibrary">영상 보기</button>
          </article>
        </div>
        <div class="fc-sticky-action"><button class="fc-btn fc-btn-primary" @click="openVideoLibrary">운동 영상으로 시작</button></div>
      </div>

      <!-- VIDEO -->
      <div class="fc-body fc-page-video" v-if="page==='video'">
        <button class="fc-nav-back" @click="go('recommend')">← 이전</button>
        <h1 class="fc-h1">국민체력100 운동 영상</h1>
        <span class="fc-badge fc-badge-good">AI Fitness DB · 국민체력100 공식 영상</span>
        <div class="fc-section-divider"></div>
        <p v-if="videoLoading" class="fc-sub">영상 DB를 불러오는 중입니다…</p><p v-if="videoError" class="fc-error">{{ videoError }}</p>
        <div class="fc-video-card" v-for="v in dbVideos" :key="v.url">
          <div class="fc-video-media"><measurement-video-player v-if="youtubeGuideFor(v)" :key="youtubeGuideFor(v).youtubeId" :guide="youtubeGuideFor(v)"></measurement-video-player><p v-else class="fc-video-unavailable">현재 재생할 수 없는 영상입니다.</p></div>
          <div class="fc-video-title">{{ v.title }}</div><div class="fc-video-meta">{{ v.display_group }} · {{ v.age_group }} · {{ v.exercise_name }}</div>
        </div>
      </div>

      <button v-if="page==='report'" ref="chatTrigger" class="fc-chat-fab" type="button"
        aria-label="체력코치 AI에게 질문하기" @click="openChat"><img src="./assets/fitness-coach-chatbot.png" alt="" aria-hidden="true"></button>
      <aside v-if="chatSidebarOpen" class="fc-chat-panel" role="dialog" aria-modal="true"
        aria-labelledby="chat-panel-title" @keydown.stop="handleChatDialogKeydown">
        <header class="fc-chat-head"><div><span class="fc-badge fc-badge-good">AI FITNESS COACH</span><h2 id="chat-panel-title">체력코치 AI</h2></div><button type="button" class="fc-drawer-close" @click="closeChat" aria-label="채팅 닫기">×</button></header>
        <div class="fc-chat-messages" aria-live="polite">
          <div v-for="(message,index) in chatMessages" :key="index" :class="['fc-chat-bubble',message.role]">{{ message.content }}</div>
          <div v-if="chatLoading" class="fc-chat-bubble assistant">답변을 준비하고 있습니다…</div>
        </div>
        <form class="fc-chat-form" @submit.prevent="sendChat"><input ref="chatInput" class="fc-input" v-model="chatInput" maxlength="500" autocomplete="off" placeholder="질문 입력" aria-label="질문 입력"><button class="fc-btn fc-btn-primary" type="submit" :disabled="chatLoading || !chatInitialized || !chatInput.trim()">전송</button></form>
      </aside>

    </div>

    <div class="fc-drawer-backdrop" v-if="videoSidebarOpen || guideSidebarOpen || measurementVideoSidebarOpen" @click="videoSidebarOpen=false;guideSidebarOpen=false;measurementVideoSidebarOpen=false"></div>
    <div class="fc-chat-backdrop" v-if="chatSidebarOpen" @click="closeChat"></div>
    <aside class="fc-drawer" v-if="guideSidebarOpen && selectedMeasureGuide" role="dialog" aria-modal="true" aria-label="측정 가이드 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-primary">HOME GUIDE</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedMeasureGuide.name }}</h2></div><button class="fc-drawer-close" @click="guideSidebarOpen=false" aria-label="닫기">×</button></div>
      <p class="fc-sub">{{ selectedMeasureGuide.why }}</p><dl class="fc-guide-copy"><dt>준비물</dt><dd>{{ selectedMeasureGuide.prep }}</dd><dt>필요한 공간</dt><dd>{{ selectedMeasureGuide.space }}</dd><dt>측정 방법</dt><dd>{{ selectedMeasureGuide.method }}</dd><dt>주의사항</dt><dd>{{ selectedMeasureGuide.caution }}</dd><template v-if="selectedMeasureGuide.note"><dt>측정 오차 핵심 기준</dt><dd>{{ selectedMeasureGuide.note }}</dd></template></dl>
    </aside>
    <aside class="fc-drawer" v-if="measurementVideoSidebarOpen && selectedMeasurementVideo" role="dialog" aria-modal="true" aria-label="측정 방법 동영상 가이드 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-good">MEASUREMENT VIDEO</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedMeasurementVideo.measurementName }}</h2></div><button class="fc-drawer-close" @click="measurementVideoSidebarOpen=false" aria-label="닫기">×</button></div>
      <p class="fc-sub">측정을 시작하기 전에 동작과 주의사항을 영상으로 확인해 보세요.</p>
      <measurement-video-player :key="selectedMeasurementVideo.youtubeId" :guide="selectedMeasurementVideo"></measurement-video-player>
      <p class="fc-measure-video-note">영상 시청 전후에도 측정 가이드의 준비물·공간·주의사항을 함께 확인해 주세요.</p>

    </aside>
    <aside class="fc-drawer" v-if="videoSidebarOpen" role="dialog" aria-modal="true" aria-label="운동 동영상 사이드바">
      <div class="fc-drawer-head"><div><span class="fc-badge fc-badge-primary">DB 영상 TOP 3</span><h2 class="fc-h2" style="margin:8px 0 0">{{ selectedVideoLabel }} 동영상 가이드</h2></div><button class="fc-drawer-close" @click="videoSidebarOpen=false" aria-label="닫기">×</button></div>
      <p v-if="videoLoading" class="fc-sub">영상 DB를 조회하는 중입니다…</p><p v-if="videoError" class="fc-error">{{ videoError }}</p>
      <div class="fc-drawer-video" v-for="(video,index) in dbVideos" :key="video.url"><strong>{{ index+1 }}. {{ video.title }}</strong><p class="fc-sub" style="margin:5px 0 10px">{{ video.description || '국민체력100 공식 운동 영상' }}</p><measurement-video-player v-if="youtubeGuideFor(video)" :key="youtubeGuideFor(video).youtubeId" :guide="youtubeGuideFor(video)"></measurement-video-player><p v-else class="fc-error">YouTube 영상 주소가 없어 웹뷰에서 재생할 수 없습니다.</p></div>
    </aside>

  </div>
  `,
};

const app = createApp(App);
app.mount("#app");
