/*
 * 地区分组脚本（极简版）｜Hako
 *
 * 职责（只做动态部分，不碰 Rules / DNS / TUN）：
 *  1. 按节点名正则划分地区，生成地区 Auto 组（url-test）
 *  2. 生成 US-Manual / US-Meta / EUR-Manual（select，复用同地区成员）
 *  3. 生成 APNs-Fallback / 🌍 Global-Fallback（依赖地区组）
 *  4. 按每组精选表把地区选项插入 PROXY-Gate / 服务策略组
 *     （Apple Push 为静态 fallback，脚本不碰）
 *
 * 配合 whisper-scheme.yaml（规则方案）使用：
 *  - 应用顺序：规则方案先，脚本后（Hako 按"规则方案 → 覆写脚本"顺序）
 *  - 幂等：重复执行不会越插越多（动态选项先清后插）
 *  - 去掉本脚本，规则方案仍可独立工作（服务组只是少了地区选项）
 */

function main(config) {
  var proxies = (config && Array.isArray(config.proxies)) ? config.proxies : [];
  var names = proxies.map(function (p) {
    return typeof p === "string" ? p : (p && p.name);
  }).filter(Boolean);

  var regionGroups = [
    { name: "🇺🇸 US", filter: /([\[]US[\]]|^US$|USA|United[ _-]?States|\bUS\b|美国|美國|🇺🇸)/i },
    { name: "🇸🇬 SG", filter: /([\[]SG[\]]|^SG$|Singapore|\bSG\b|新加坡|狮城|🇸🇬)/i },
    { name: "🇭🇰 HK", filter: /([\[]HK[\]]|^HK$|Hong[ _-]?Kong|\bHK\b|香港|🇭🇰)/i },
    { name: "🇲🇴 MO", filter: /([\[]MO[\]]|^MO$|Macau|Macao|\bMO\b|澳门|澳門|🇲🇴)/i },
    { name: "🇯🇵 JP", filter: /([\[]JP[\]]|^JP$|Japan|\bJP\b|日本|东京|大阪|🇯🇵)/i },
    { name: "🇹🇼 TW", filter: /([\[]TW[\]]|^TW$|Taiwan|Taibei|Taipei|\bTW\b|台湾|臺灣|台北|高雄|🇹🇼)/i },
    { name: "🇬🇧 UK", filter: /([\[]UK[\]]|^UK$|United[ _-]?Kingdom|Britain|England|\bUK\b|英国|英國|伦敦|🇬🇧)/i },
    { name: "🇩🇪 DE", filter: /([\[]DE[\]]|^DE$|Germany|Deutschland|\bDE\b|德国|德國|法兰克福|🇩🇪)/i },
    { name: "🇫🇷 FR", filter: /([\[]FR[\]]|^FR$|France|\bFR\b|法国|法國|巴黎|🇫🇷)/i },
    { name: "🇷🇺 RU", filter: /([\[]RU[\]]|^RU$|Russia|Russian[ _-]?Federation|\bRU\b|俄罗斯|俄羅斯|莫斯科|伯力|🇷🇺)/i },
    { name: "🇨🇦 CA", filter: /([\[]CA[\]]|^CA$|Canada|\bCA\b|加拿大|🇨🇦)/i },
    { name: "🇦🇺 AU", filter: /([\[]AU[\]]|^AU$|Australia|\bAU\b|澳大利亚|澳洲|澳大利亞|🇦🇺)/i },
    { name: "🇰🇷 KR", filter: /([\[]KR[\]]|^KR$|Korea|South[ _-]?Korea|\bKR\b|韩国|韓國|首尔|首爾|🇰🇷)/i },
    { name: "🇮🇹 IT", filter: /([\[]IT[\]]|^IT$|Italy|Italian|\bIT\b|意大利|義大利|米兰|米蘭|罗马|羅馬|🇮🇹)/i },
    { name: "🇪🇸 ES", filter: /([\[]ES[\]]|^ES$|Spain|Spanish|\bES\b|西班牙|马德里|馬德里|🇪🇸)/i },
    { name: "🇳🇱 NL", filter: /([\[]NL[\]]|^NL$|Netherlands|Dutch|\bNL\b|荷兰|荷蘭|阿姆斯特丹|🇳🇱)/i },
    { name: "🇫🇮 FI", filter: /([\[]FI[\]]|^FI$|Finland|Finnish|\bFI\b|芬兰|芬蘭|赫尔辛基|赫爾辛基|🇫🇮)/i },
    { name: "🇳🇴 NO", filter: /([\[]NO[\]]|^NO$|Norway|Norwegian|\bNO\b|挪威|奥斯陆|奧斯陸|🇳🇴)/i },
    { name: "🇸🇪 SE", filter: /([\[]SE[\]]|^SE$|Sweden|Swedish|\bSE\b|瑞典|斯德哥尔摩|斯德哥爾摩|🇸🇪)/i },
    { name: "🇨🇭 CH", filter: /([\[]CH[\]]|^CH$|Switzerland|Swiss|\bCH\b|瑞士|苏黎世|蘇黎世|日内瓦|日內瓦|🇨🇭)/i },
    { name: "🇵🇱 PL", filter: /([\[]PL[\]]|^PL$|Poland|Polish|\bPL\b|波兰|波蘭|华沙|華沙|🇵🇱)/i },
    { name: "🇮🇳 IN", filter: /([\[]IN[\]]|^IN$|India|Indian|\bIN\b|印度|🇮🇳)/i },
    { name: "🇵🇭 PH", filter: /([\[]PH[\]]|^PH$|Philippines|Filipino|\bPH\b|菲律宾|菲律賓|马尼拉|馬尼拉|🇵🇭)/i },
    { name: "🇻🇳 VN", filter: /([\[]VN[\]]|^VN$|Vietnam|Vietnamese|\bVN\b|越南|河内|河內|胡志明|🇻🇳)/i },
    { name: "🇲🇾 MY", filter: /([\[]MY[\]]|^MY$|Malaysia|Malaysian|\bMY\b|马来西亚|馬來西亞|吉隆坡|🇲🇾)/i }
  ];
  var AUTO_ICON = "https://raw.githubusercontent.com/Koolson/Qure/master/IconSet/Color/Auto.png";

  if (!Array.isArray(config["proxy-groups"])) config["proxy-groups"] = [];
  var groups = config["proxy-groups"];
  var byName = {};
  groups.forEach(function (g) { if (g && g.name) byName[g.name] = g; });

  // ---- 1. 地区 Auto 组 ----
  var existingAutos = [];
  regionGroups.forEach(function (r) {
    var matched = names.filter(function (n) { return r.filter.test(n); });
    if (matched.length < 1) return;
    var autoName = r.name + "-Auto";
    if (!byName[autoName]) {
      var g = {
        name: autoName,
        type: "url-test",
        icon: AUTO_ICON,
        proxies: matched,
        url: "https://www.gstatic.com/generate_204",
        interval: 7200,
        tolerance: 50
      };
      groups.push(g);
      byName[autoName] = g;
    } else {
      byName[autoName].proxies = matched; // 节点更新后刷新成员
    }
    existingAutos.push(autoName);
  });

  function upsertGroupLater(name, type, proxies, icon) {
    if (byName[name]) { byName[name].proxies = proxies; return; }
    var g = { name: name, type: type, proxies: proxies };
    if (icon) g.icon = icon;
    groups.push(g);
    byName[name] = g;
  }

  // ---- 2. Manual / Meta / EUR 组 ----
  var usAuto = byName["🇺🇸 US-Auto"];
  if (usAuto) {
    upsertGroupLater("🇺🇸 US-Manual", "select", usAuto.proxies.slice(),
      "https://fastly.jsdelivr.net/gh/Koolson/Qure/IconSet/Color/United_States.png");
    upsertGroupLater("🇺🇸 US-Meta", "select", usAuto.proxies.slice(),
      "https://fastly.jsdelivr.net/gh/Koolson/Qure/IconSet/Color/United_States.png");
  }
  var eurMembers = ["🇬🇧 UK-Auto", "🇩🇪 DE-Auto", "🇫🇷 FR-Auto"]
    .filter(function (n) { return byName[n]; });
  if (eurMembers.length) {
    upsertGroupLater("🗺️ EUR-Manual", "select", eurMembers,
      "https://fastly.jsdelivr.net/gh/Koolson/Qure/IconSet/Color/Europe_Map.png");
  }

  // ---- 3. APNs-Fallback / Global-Fallback ----
  function upsertGroup(name, type, proxies, url, interval) {
    if (byName[name]) { byName[name].proxies = proxies; return; }
    var g = { name: name, type: type, proxies: proxies, url: url, interval: interval };
    groups.push(g);
    byName[name] = g;
  }
  var hasAutos = existingAutos.length > 0;
  if (hasAutos) {
    upsertGroup("APNs-Fallback", "fallback", existingAutos.slice(),
      "https://captive.apple.com/hotspot-detect.html", 900);
    upsertGroup("🌍 Global-Fallback", "fallback", existingAutos.slice(),
      "https://www.gstatic.com/generate_204", 43200);
    // Apple Push: inline region autos directly (Hako drops nested fallback refs)
    var applePush = byName["Apple Push"];
    if (applePush) applePush.proxies = ["Apple"].concat(existingAutos, ["DIRECT"]);
  }

  // ---- 3. 选项注入（幂等） ----
  var DYNAMIC = ["🌍 Global-Fallback", "APNs-Fallback",
    "🇺🇸 US-Manual", "🇺🇸 US-Meta", "🗺️ EUR-Manual"].concat(
    regionGroups.map(function (r) { return r.name + "-Auto"; })
  );
  function stripDynamic(list) {
    return list.filter(function (x) { return DYNAMIC.indexOf(x) === -1; });
  }
  function injectAfter(groupName, after, items) {
    var g = byName[groupName];
    if (!g || !Array.isArray(g.proxies) || !items.length) return;
    var list = stripDynamic(g.proxies.filter(function (x) { return typeof x === "string"; }));
    var idx = list.indexOf(after);
    var at = idx === -1 ? list.length : idx + 1;
    items.forEach(function (it, i) {
      if (list.indexOf(it) === -1) list.splice(at + i, 0, it);
    });
    g.proxies = list;
  }
  function injectBefore(groupName, before, items) {
    var g = byName[groupName];
    if (!g || !Array.isArray(g.proxies) || !items.length) return;
    var list = stripDynamic(g.proxies.filter(function (x) { return typeof x === "string"; }));
    var idx = list.indexOf(before);
    var at = idx === -1 ? 0 : idx;
    items.forEach(function (it, i) {
      if (list.indexOf(it) === -1) list.splice(at + i, 0, it);
    });
    g.proxies = list;
  }

  function exists(n) { return byName[n] ? n : null; }
  function pick(list) {
    return list.map(exists).filter(Boolean);
  }

  // 每组精选地区（只注入存在的组；不在表的用 DEFAULT）
  var DEFAULT_REGIONS = ["🇺🇸 US-Auto", "🇸🇬 SG-Auto", "🇭🇰 HK-Auto",
    "🇯🇵 JP-Auto", "🇹🇼 TW-Auto", "🗺️ EUR-Manual"];
  var AI_REGIONS = ["🇺🇸 US-Auto", "🇺🇸 US-Manual", "🇸🇬 SG-Auto",
    "🇭🇰 HK-Auto", "🇯🇵 JP-Auto", "🇹🇼 TW-Auto", "🗺️ EUR-Manual"];
  var CURATED = {
    "Apple": ["🇺🇸 US-Auto", "🇺🇸 US-Manual"],
    "X": ["🇺🇸 US-Auto", "🇺🇸 US-Manual"],
    "Meta": ["🇺🇸 US-Auto", "🇺🇸 US-Meta"],
    "Threads": ["🇺🇸 US-Auto", "🇺🇸 US-Meta"],
    "GPT": AI_REGIONS,
    "Gemini": AI_REGIONS,
    "Grok": AI_REGIONS,
    "Microsoft": [],
    "OneDrive": [],
    "Outlook": []
  };

  // PROXY-Gate: [🖥️ All-Nodes, 🌍 Auto, (Global-Fallback, EUR, US/SG/HK/JP/TW...), DIRECT]
  if (hasAutos) {
    injectAfter("PROXY-Gate", "🌍 Auto",
      ["🌍 Global-Fallback"].concat(pick(DEFAULT_REGIONS)));
  }
  // 服务组: [🖥️ All-Nodes, 🌍 Auto, (Global-Fallback, 精选地区...), PROXY-Gate, DIRECT]
  // Apple Push 为静态 fallback，脚本不注入
  var serviceNames = ["YouTube", "Netflix", "Disney+", "Emby", "Spotify",
    "TikTok", "Twitch", "GPT", "Gemini", "Claude", "Grok", "Microsoft",
    "Google", "Apple", "iCloud", "Amazon", "Meta", "X", "Threads", "WhatsApp",
    "Telegram", "Github", "Speedtest", "OneDrive", "Outlook"];
  serviceNames.forEach(function (n) {
    if (!hasAutos) return;
    var list = Object.prototype.hasOwnProperty.call(CURATED, n)
      ? CURATED[n] : DEFAULT_REGIONS;
    injectAfter(n, "🌍 Auto",
      ["🌍 Global-Fallback"].concat(pick(list)));
  });

  return config;
}
