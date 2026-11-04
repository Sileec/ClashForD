/*
 * 地区分组脚本（极简版）｜Used for ClashbyClash
 *
 * 职责（只做动态部分，不碰 Rules / DNS / TUN）：
 *  1. 按节点名正则划分地区，生成地区 Auto 组（url-test）
 *  2. 节点少于2个不自动生成地区 Auto 组
 *  2. 生成 APNs-Fallback / 🌍 Global-Fallback（依赖地区组）
 *  3. 把已存在的地区组插入 PROXY-Gate / Apple Push / 服务策略组的选项
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
    if (matched.length < 2) return;
    var autoName = r.name + "-Auto";
    if (!byName[autoName]) {
      var g = {
        name: autoName,
        type: "url-test",
        icon: AUTO_ICON,
        proxies: matched,
        url: "http://www.gstatic.com/generate_204",
        interval: 900,
        tolerance: 50
      };
      groups.push(g);
      byName[autoName] = g;
    } else {
      byName[autoName].proxies = matched; // 节点更新后刷新成员
    }
    existingAutos.push(autoName);
  });

  // ---- 2. APNs-Fallback / Global-Fallback ----
  function upsertGroup(name, type, proxies, url, interval) {
    if (byName[name]) { byName[name].proxies = proxies; return; }
    var g = { name: name, type: type, proxies: proxies, url: url, interval: interval };
    groups.push(g);
    byName[name] = g;
  }
  var hasAutos = existingAutos.length > 0;
  if (hasAutos) {
    upsertGroup("APNs-Fallback", "fallback", existingAutos.slice(),
      "http://captive.apple.com/hotspot-detect.html", 300);
    upsertGroup("🌍 Global-Fallback", "fallback", existingAutos.slice(),
      "http://www.gstatic.com/generate_204", 600);
  }

  // ---- 3. 选项注入（幂等） ----
  var DYNAMIC = ["🌍 Global-Fallback", "APNs-Fallback"].concat(
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

  var regionInserts = hasAutos ? ["🌍 Global-Fallback"].concat(existingAutos) : [];

  // PROXY-Gate: [🖥️ All-Nodes, 🌍 Auto, (Global-Fallback, 地区Auto...), DIRECT]
  injectAfter("PROXY-Gate", "🌍 Auto", regionInserts);
  // Apple Push: [(APNs-Fallback), 🌍 Auto, 🖥️ All-Nodes, DIRECT]
  if (hasAutos) injectBefore("Apple Push", "🌍 Auto", ["APNs-Fallback"]);
  // 服务组: [🖥️ All-Nodes, 🌍 Auto, (Global-Fallback, 地区Auto...), PROXY-Gate, DIRECT]
  var serviceNames = ["YouTube", "Netflix", "Disney+", "Emby", "Spotify",
    "TikTok", "Twitch", "GPT", "Gemini", "Claude", "Grok", "Microsoft",
    "Google", "Apple", "iCloud", "Amazon", "Meta", "X", "Threads", "WhatsApp",
    "Telegram", "Github", "Speedtest"];
  serviceNames.forEach(function (n) { injectAfter(n, "🌍 Auto", regionInserts); });

  return config;
}
