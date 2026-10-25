// 自然对话准则 · 观察 + 有限干预（P3）
//
// 三个扩展点：
//   1. manifest 的 prompt.sections —— 往系统提示里加一段「怎么说话」；
//   2. hooks['before-send'] —— 发送前给 PASS / WARN / REVISE / SUPPRESS；
//   3. hooks['after-tool'] —— 记录实际发出的文本，供跨句统计。
//
// 明确边界（对应 docs/natural-dialogue/ 的负向规则库）：
//   - 默认 observe：只记录，不改写、不拦截；
//   - assist 模式才会改，且只在 scopes 指定的会话里生效；
//   - REVISE 只删固定起手式和硬加的结尾反问，不加内容、不改事实；
//   - SUPPRESS 只处理“连续同类短句”，明确 @/提问/私聊一律不压；
//   - 反对的是高频机械复用，不是汉语本身；技术语境的“不是 A 而是 B”不算模板。

let cfg = () => ({});
let log = () => {};

export function setup(api) {
  cfg = api?.config || (() => ({}));
  log = api?.log || (() => {});
}

const SELF_DEPRECATION = /你说我.{1,8}我认|我(菜|笨|傻|蠢)我认|蹭你的.{0,8}不挑|花你的.{0,8}不挑|我(虽然)?(是|不过)(个)?(AI|ai|人工智能|机器人).{0,12}(但|不过)|我这种人(就)?(这样|活该)/;
const FORMULAIC_REVERSAL = /不是[^，,。！？\n]{1,12}[，,]\s*(而)?是|不在[^，,。！？\n]{1,12}了[，,]\s*(而)?是|你以为[^，,。！？\n]{1,12}[，,]\s*(其实|实际|结果)|表面(上)?[^，,。！？\n]{1,10}[，,]\s*(背地|实际|其实)/;
// 认命式对偶：「该漏的还是漏」「我该删的还是删」。本机真实发言里连续出现，是成套复用的公式。
// 只记录，不自动删——删掉后半句会丢态度。
const STOIC_REFRAIN = /该[^，。！？\n]{1,6}(的)?还是[^，。！？\n]{1,6}/;
const PRESET_AGREEMENT = /^(确实|我懂|看得出来|理解你|能理解|辛苦了|抱抱|摸摸)[，,。！!]?/;
const TRAILING_QUESTION = /(你觉得呢|你怎么看|要不要我.{0,10}|需要我.{0,8}吗|对吧|是吧|你说呢)[?？。.!！]?\s*$/;
// 固定起手式：本机 2343 条历史发言里，「好家伙」34 次、「行吧」26 次、「行行行」18 次。
// 只统计近 6 条内重复的开场，不把一次性语气词算进来。
const OPENING_STRIP = /^[\s[（(【"'“”]+|^(哈+|嗯+|哦+|啊+|哎+|诶+)/;
// 翻译腔：中文里不自然的直译结构。只认高置信短语，不把正常书面表达一网打尽。
// 来源：2026-10-22 私聊样本里的“互相训练彼此”“全链路都换成 AI”“说回正事”“被点出来了”。
const TRANSLATIONESE = /互相[^，。！？\n]{0,4}彼此|被拿来当[^，。！？\n]{0,6}(素材|例子|证据|理由)|谁在看谁|说回正事|换个正经的|被点出来了|会有点意识|全链路(都|全)?(换|是|用)/;
// 认错/认领式收尾：客服腔的“我认”“我接”“我承认”，用一句认领代替说清哪句有问题。
// 只认句尾或独立短句，避免误伤“我承认这版做得不好，但…”这类正常表达。
const ADMISSION_TEMPLATE = /([，,]\s*)?(我认|我接下了?|我承认)[。！!～~]?\s*$|这(句|个)(话)?我认/;
// 接梗式认领：机器人不会玩梗，硬接只会变成「那我收下了」「这梗我接了」这种表演。
// 只认明确接梗的固定说法，不把正常讨论「玩梗」的内容当成违规。
const BIT_ACK = /(那)?我收下了|这梗我接了|这个梗我接|这梗我懂|我懂这个梗|接住这个梗/;
// 清单腔：把建议写成“两件事/三个办法/第一第二”，群聊里像汇报。
const LIST_TONE = /先看(两|三|几)件事|(两|三|几)个(办法|建议|点)[：:]|第一[，,].{0,60}第二[，,]/;
// 起手式填充：单次就该收，不等重复。「行，讲个真的」→「讲个真的」。
const OPENING_FILLER = /^(行吧|行行行|行|好家伙|说实话|老实说|早说了|早就说了)[，,]/;
// 句中独立成句的「矛盾了是吧。」——不是消息结尾，旧规则只看句尾，会漏。
// 只认句号/感叹号前的「是吧/对吧」，问号前的当真实疑问处理。
const INLINE_TAG_QUESTION = /[^，。！？\n]{2,12}(是吧|对吧)[。！]/;
// 搭架子式表达：先铺一句立场再进正题，是书面/翻译腔的常见骨架。
// 「说实话」「对我来说」是填充，「得看 X 怎么定义」是概念拆解，「关键是」是汇报式收尾。
const FILLER_TEMPLATE = /说实话|老实说|对我来说|得看[^，。！？\n]{0,8}怎么(定义|算|看)|看你怎么定义|关键是|关键在于|说白了|说穿了|归根结底/;
// 标点写成文章：破折号、省略号、分号。群聊里只用逗号、句号、问号、感叹号。
const PUNCT_HEAVY = /——|……|\.{3,}|；/;
// 虚构自己的现实行为：AI 会顺口编「我刚在玩手机」「我躺着」这类生活细节。
// 只认明确的现实动作，不碰「我刚看到消息」这类可成立的说法。
const FABRICATED_SELF_ACT = /我(刚|刚才|刚刚)(在)?(玩手机|刷手机|躺着|吃完饭|下班|上班|睡觉)|我(正|现在)(在)?(玩手机|刷手机|吃饭|上班|躺着)|我(躺|趴)在(床|沙发)/;
// 陪伴宣言和服务腔：不解决具体问题，只表态度或让用户继续点单。
const COMFORT_SLOGAN = /我在这儿|我听着|我一直陪着你|我会一直陪着你|我一直都在|想听什么|想听啥|想聊啥|想要什么图|说一声|直接报歌名/;
// 离世安慰里最容易说错的句式：暗示它活着是受罪，或者替对方宣布“解脱”。
const HARMFUL_COMFORT = /不用再受罪|跟着你.{0,8}受罪|总算是解脱了|对它也是解脱/;
// 认错后多余的承诺：承认就完了，别加「我改」「下次注意」「刚才那句当没说过」。
const REPAIR_PROMISE = /[，,]\s*(我改|我会改|下次注意)[。！!]?\s*$|[，,]\s*改[。！!]?\s*$|刚才那句就当没说过[。！!]?/;
// 先解析词：对方拿一个说法说事，模型先停下来拆词义、问“你指的是哪种”。
// 不是禁止解释术语——对方明确问“什么是 X”时该解释；这里标记的是把定义当开场白。
const CONCEPT_PARSE = /你说的?[^。！？\n]{1,12}(是指|指的是|是什么意思|指什么|是哪种|指哪种)|所谓的?[^。！？\n]{1,12}(是指|意思是)|这个词[^。！？\n]{0,12}(是指|的意思|怎么理解)|按(我|你)的理解|有人(是)?说[^。！？\n]{0,40}有人(是)?说|(一种|第一种)[^。！？\n]{0,24}(另一种|第二种)/;
const LECTURE_SERIES = /首先.{0,40}其次/;
const LECTURE_SUMMARY = /综上|总的来说|总而言之/;
// 技术排查里的"不是 X，是 Y"是在纠错，不是模板反转。词表按本机真实技术对话补过：
// 编码/字符/管道/进程/服务/依赖/证书/显卡等，都是群里实际出现过的排查语境。
const TECH_CONTEXT = /报错|错误|异常|蓝屏|崩溃|配置|代码|参数|接口|版本|安装|驱动|端口|日志|编码|字符|管道|进程|服务|依赖|证书|显卡|内存|磁盘|路径|退出|重启|部署|编译|数据库|网络|怎么(办|弄|修|解决)|如何|为什么/;

const ACT_ACK = /^(嗯|哦|啊|哈|好|行|ok|OK|收到|在)\s*[。.!！~～]?$/;
const ACT_AGREE = /^(确实|对啊|就是|同意|有道理|没错|是这样的)/;
const ACT_TEASE = /笑死|绷|草|典|急了|乐|离谱|逆天|绝了|麻了|好家伙/;
const ACT_ASK = /[?？]\s*$/;

export function dialogueAct(text) {
  const t = String(text || '').trim();
  if (!t) return 'empty';
  if (ACT_ACK.test(t)) return 'ack';
  if (ACT_AGREE.test(t)) return 'agree';
  if (ACT_ASK.test(t)) return 'ask';
  if (ACT_TEASE.test(t)) return 'tease';
  return 'statement';
}

function repeated(history, pattern, limit = 2) {
  return history.slice(-4).filter((t) => t && pattern.test(t)).length >= limit;
}

/** 取开场的前两个字，剥掉标点、括号和纯语气词，用于判断固定起手式。 */
function openingOf(text) {
  return String(text || '').trim().replace(OPENING_STRIP, '').slice(0, 2);
}

/**
 * P3 的词面修订：只做删除，不添加、不改写事实。
 * 返回 null 表示不该改（删完太短、语义会变、或没有命中）。
 */
export function reviseText(text, flags = []) {
  let out = String(text || '').trim();
  if (!out) return null;
  const codes = new Set((Array.isArray(flags) ? flags : []).map((f) => f?.code ?? f));

  if (codes.has('OPENING_HABIT') || codes.has('OPENING_FILLER')) {
    const stripped = out.replace(/^(行吧|行行行|行|好家伙|说实话|老实说|早说了|早就说了|嗯+|哦+|啊+|哎+|诶+)[，,。！!\s～~]+/, '').trim();
    if (stripped.length >= 4 && stripped !== out) out = stripped;
  }
  if (codes.has('TRAILING_QUESTION') && out.length >= 5) {
    // 句号保留（「矛盾了是吧。」→「矛盾了。」），问号属于反问本身，一起删掉。
    const stripped = out.replace(/[，,]?\s*(是吧|对吧|你觉得呢|你说呢)([?？。.!！])?\s*$/, (_, _q, end) => (end && end !== '?' && end !== '？' ? end : '')).trim();
    if (stripped.length >= 4 && stripped !== out && !/[，,、]$/.test(stripped)) out = stripped;
  }
  if (codes.has('INLINE_TAG_QUESTION')) {
    // 「矛盾了是吧。那我换个说法」→「矛盾了。那我换个说法」，只删口头禅，保留句读。
    out = out.replace(/([^，。！？\n]{2,12})(是吧|对吧)([。！])/g, '$1$3');
  }
  if (codes.has('REPAIR_PROMISE')) {
    // 「知道了，我改。」→「知道了。」；「…太多次了，改。」→「…太多次了。」
    const stripped = out
      .replace(/([，,])\s*(我改|我会改|下次注意)([。！!]?)/g, '$3')
      .replace(/([，,])\s*改([。！!]?)/g, '$2')
      .replace(/刚才那句就当没说过[。！!]?/g, '')
      .replace(/[，,]{2,}/g, '，')
      .trim();
    if (stripped.length >= 4) out = stripped;
  }
  if (codes.has('BIT_ACK')) {
    // 删掉接梗的认领句，保留前后事实；顺手合并因此产生的重复逗号。
    const stripped = out
      .replace(/(那)?我收下了/g, '')
      .replace(/这梗我接了|这个梗我接|这梗我懂|我懂这个梗|接住这个梗/g, '')
      .replace(/[，,]{2,}/g, '，')
      .replace(/^[，,]\s*/, '')
      .replace(/\s*[，,]\s*$/, '')
      .trim();
    if (stripped.length >= 4) out = stripped;
  }
  // 认错收尾只删句尾那一小截，保留前面的事实陈述；删完整句太短就不动。
  if (codes.has('ADMISSION_TEMPLATE')) {
    const stripped = out.replace(/[，,]\s*我(认|接下了?|承认)[。！!～~]?\s*$/, '').trim();
    if (stripped.length >= 4 && stripped !== out) out = stripped;
  }
  return out === String(text || '').trim() ? null : out;
}

/** 干预范围：空 = 不干预（必须显式列群/会话，避免一开就影响所有群）。 */
export function inScope(cfgValue, chatKey) {
  const raw = cfgValue?.scopes;
  const list = Array.isArray(raw)
    ? raw.map(String)
    : String(raw || '').split(/[\s,，]+/);
  const scopes = list.map((s) => s.trim()).filter(Boolean);
  if (!scopes.length) return false;
  const key = String(chatKey || '');
  const id = key.includes(':') ? key.split(':').pop() : key;
  return scopes.includes(key) || scopes.includes(id);
}

/** 返回 [{ code, confidence, detail }]；空数组表示没发现值得记录的问题。 */
export function check(text, history = []) {
  const t = String(text || '').trim();
  if (!t) return [];
  const hist = (Array.isArray(history) ? history : []).filter(Boolean);
  const tech = TECH_CONTEXT.test(t);
  const flags = [];

  if (SELF_DEPRECATION.test(t)) {
    flags.push({ code: 'SELF_DEPRECATION', confidence: repeated(hist, SELF_DEPRECATION) ? 0.85 : 0.45, detail: '自嘲/认错骨架' });
  }
  if (!tech && FORMULAIC_REVERSAL.test(t)) {
    flags.push({ code: 'FORMULAIC_REVERSAL', confidence: repeated(hist, FORMULAIC_REVERSAL) ? 0.8 : 0.55, detail: '不是A而是B式反转' });
  }
  if (TRANSLATIONESE.test(t)) {
    flags.push({ code: 'TRANSLATIONESE', confidence: repeated(hist, TRANSLATIONESE) ? 0.7 : 0.5, detail: '直译腔/名词化结构' });
  }
  if (ADMISSION_TEMPLATE.test(t)) {
    flags.push({ code: 'ADMISSION_TEMPLATE', confidence: repeated(hist, ADMISSION_TEMPLATE) ? 0.8 : 0.65, detail: '认错/认领式收尾' });
  }
  if (LIST_TONE.test(t)) {
    flags.push({ code: 'LIST_TONE', confidence: 0.6, detail: '清单腔/汇报式分点' });
  }
  if (STOIC_REFRAIN.test(t)) {
    flags.push({ code: 'STOIC_REFRAIN', confidence: repeated(hist, STOIC_REFRAIN) ? 0.75 : 0.5, detail: '「该X还是X」套句' });
  }
  if (BIT_ACK.test(t)) {
    flags.push({ code: 'BIT_ACK', confidence: 0.6, detail: '硬接梗/认领式回应' });
  }
  // 「嗯……」「我想想……」是拟人的思考停顿，不算标点滥用，先剥掉再查。
  if (PUNCT_HEAVY.test(t.replace(/(^|\n)\s*(嗯+|唔+|哦+|啊+|我想想|让我想想|等我想想)[…\.]{2,}/g, '$1'))) {
    flags.push({ code: 'PUNCT_HEAVY', confidence: 0.5, detail: '破折号/省略号/分号偏多' });
  }
  if (FABRICATED_SELF_ACT.test(t)) {
    flags.push({ code: 'FABRICATED_SELF_ACT', confidence: 0.7, detail: '虚构自己的现实行为' });
  }
  if (COMFORT_SLOGAN.test(t)) {
    flags.push({ code: 'COMFORT_SLOGAN', confidence: 0.55, detail: '陪伴宣言/服务腔' });
  }
  if (HARMFUL_COMFORT.test(t)) {
    flags.push({ code: 'HARMFUL_COMFORT', confidence: 0.75, detail: '暗示逝者活着受罪' });
  }
  if (REPAIR_PROMISE.test(t)) {
    flags.push({ code: 'REPAIR_PROMISE', confidence: 0.6, detail: '认错后的多余承诺' });
  }
  if (OPENING_FILLER.test(t)) {
    flags.push({ code: 'OPENING_FILLER', confidence: 0.6, detail: '“行，”式起手' });
  }
  if (FILLER_TEMPLATE.test(t)) {
    flags.push({ code: 'FILLER_TEMPLATE', confidence: repeated(hist, FILLER_TEMPLATE) ? 0.7 : 0.5, detail: '搭架子式填充/概念拆解' });
  }
  if (CONCEPT_PARSE.test(t)) {
    flags.push({ code: 'CONCEPT_PARSE', confidence: 0.55, detail: '先把词拆开再回答' });
  }
  if (PRESET_AGREEMENT.test(t) && t.length >= 14) {
    flags.push({ code: 'PRESET_AGREEMENT', confidence: 0.55, detail: '先附和再展开' });
  }
  if (t.length >= 5 && TRAILING_QUESTION.test(t)) {
    flags.push({ code: 'TRAILING_QUESTION', confidence: 0.55, detail: '结尾硬加反问' });
  }
  if (INLINE_TAG_QUESTION.test(t)) {
    flags.push({ code: 'INLINE_TAG_QUESTION', confidence: 0.5, detail: '句中“是吧。”口头禅' });
  }
  if (t.length >= 6 && hist.length) {
    const open = openingOf(t);
    const used = hist.slice(-6).filter((h) => h.length >= 6 && openingOf(h) === open).length;
    if (open.length >= 2 && used >= 2) {
      flags.push({ code: 'OPENING_HABIT', confidence: 0.65, detail: `「${open}」开场近 6 条已用 ${used} 次` });
    }
  }
  if (!tech && (LECTURE_SUMMARY.test(t) || (LECTURE_SERIES.test(t) && t.length >= 24))) {
    flags.push({ code: 'LECTURE_TONE', confidence: 0.6, detail: '群聊里分点/总结' });
  }
  if (hist.length) {
    const acts = [...hist.slice(-2).map(dialogueAct), dialogueAct(t)];
    if (acts.length === 3 && acts[0] === acts[1] && acts[1] === acts[2] && ['agree', 'tease', 'ask'].includes(acts[0])) {
      flags.push({ code: 'RECENT_ACT_REUSE', confidence: 0.7, detail: `连续三条都是 ${acts[0]}` });
    }
  }
  if (t.length >= 4 && hist.length >= 2) {
    const same = hist.slice(-2).filter((h) => h.length >= 4 && h.slice(0, 4) === t.slice(0, 4)).length;
    if (same >= 2) flags.push({ code: 'REPEATED_OPENING', confidence: 0.6, detail: '连续三条同开头' });
  }
  return flags;
}

// 每个会话最近几条发送候选，只用于"连续同一动作"统计。
const history = new Map();

function recentFor(chatKey) {
  const key = String(chatKey || 'unknown');
  return history.get(key) || [];
}

function remember(chatKey, text) {
  const key = String(chatKey || 'unknown');
  const arr = history.get(key) || [];
  arr.push(text);
  if (arr.length > 8) arr.splice(0, arr.length - 8);
  history.set(key, arr);
}

function pickTexts(args) {
  const raw = args?.messages;
  if (typeof raw === 'string') return [raw];
  if (Array.isArray(raw)) return raw.map((x) => String(x ?? ''));
  return [];
}

export const hooks = {
  // 发送前：observe 只返回 PASS；assist 才可能修订/压制。
  'before-send': ({ messages, chatKey, toolName, explicitRequest } = {}) => {
    const c = cfg() || {};
    if (c.enabled === false || c.mode !== 'assist') return { action: 'PASS' };
    if (!inScope(c, chatKey)) return { action: 'PASS' };
    const texts = pickTexts({ messages });
    if (!texts.length) return { action: 'PASS' };
    const inspected = texts.slice(0, Math.max(1, Number(c.maxMessagesPerHook) || 20));

    const hist = recentFor(chatKey);
    const allFlags = [];
    const revised = [];
    let changed = false;

    for (const text of inspected) {
      const flags = check(text, hist);
      allFlags.push(...flags.map((f) => f.code));
      const next = c.reviseEnabled === false ? null : reviseText(text, flags);
      if (next) {
        changed = true;
        revised.push(next);
      } else {
        revised.push(text);
      }
    }

    // SUPPRESS 只处理“连续第三条同类短句”，且必须不是明确请求。
    if (c.suppressEnabled === true && explicitRequest === false && toolName === 'send_message'
      && inspected.length === texts.length) {
      const joined = texts.join('');
      const flags = check(joined, hist);
      const lowValue = flags.some((f) => f.code === 'RECENT_ACT_REUSE')
        && joined.length <= Math.max(4, Number(c.suppressMaxChars) || 12);
      if (lowValue) {
        return { action: 'SUPPRESS', flags: [...new Set(allFlags)], reason: '连续同类短句，本条没有新信息' };
      }
    }

    // 检查预算只限制覆盖范围；未检查的尾部消息必须原样保留。
    if (changed) return { action: 'REVISE', messages: [...revised, ...texts.slice(inspected.length)], flags: [...new Set(allFlags)] };
    if (allFlags.length) return { action: 'WARN', flags: [...new Set(allFlags)] };
    return { action: 'PASS' };
  },

  'after-tool': ({ toolName, argsRaw, session, sentTexts, suppressed } = {}) => {
    const c = cfg() || {};
    if (c.enabled === false) return;
    if (c.mode === 'off') return;
    if (toolName !== 'send_message' && toolName !== 'send_to') return;
    if (suppressed === true) return;   // 没发出去就不算一次发言
    // 仅接受发送链路确认的成功文本。失败/被拒绝时 sentTexts 为 null，
    // 不能回退 argsRaw，否则未发送的草稿会影响后续重复判定和压制。
    if (!Array.isArray(sentTexts) || !sentTexts.length) return;

    let args = {};
    try {
      args = JSON.parse(argsRaw || '{}');
    } catch {
      return;
    }
    // 部分发送成功时只观察回执中的成功部分。
    const texts = sentTexts
      .slice(0, Math.max(1, Number(c.maxMessagesPerHook) || 20));
    const chatKey = args?.targetChatKey || session?.chatKey || 'unknown';

    for (const text of texts) {
      const flags = check(text, recentFor(chatKey));
      if (flags.length) {
        log(`[natural-dialogue] ${flags.map((f) => `${f.code}:${f.confidence}`).join(',')} len=${text.length}`);
      }
      // 只记录确认发送成功的文本，用于跨句统计；不保存原文到磁盘。
      remember(chatKey, text);
    }
  }
};

/** 供离线评测或控制台调用。 */
export function reset() {
  history.clear();
}
