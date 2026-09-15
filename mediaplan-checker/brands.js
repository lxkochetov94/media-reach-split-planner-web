(function (root) {
  'use strict';
  const STORAGE_KEY = 'lab-mediaplan-checker-brands-v1';
  const COMMON_EXCLUSIONS = [
    'OLV','CPM','CPC','CTR','VTR','VK','Rutube','RuTube','RUTUBE','Hybrid','Ozon','Yandex','Яндекс',
    'RTB','Programmatic','Promopost','In-stream','Out-stream','InStream','OutStream','CTV','Smart TV',
    'AdRiver','Weborama','First Data','Digital Alliance','Telegram','TG','РСЯ','ecom','ecommerce','AdFox','Adspector'
  ];
  const DEFAULT_NAMES = ['Персил','Лоск','Вернель','Сомат','Бреф','Ласка','Шаума','Тафт','Глисс Кур','Палетт','ФА','Церезит','Момент'];

  function blankCard(name) {
    return {
      id: slug(name), name,
      lines: '', products: '', targetAudiences: '', channels: '', properPlatforms: '', correctProductNames: '',
      features: '', allowedAbbreviations: '', additionalRules: '', exclusions: ''
    };
  }
  function slug(s) { return String(s||'brand').toLowerCase().replace(/ё/g,'е').replace(/[^a-zа-я0-9]+/giu,'-').replace(/^-|-$/g,'') || `brand-${Date.now()}`; }
  function defaults() { return DEFAULT_NAMES.map(blankCard); }
  function load() {
    try {
      const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
      if (Array.isArray(parsed) && parsed.length) return parsed;
    } catch (_) {}
    const cards = defaults(); save(cards); return cards;
  }
  function save(cards) { localStorage.setItem(STORAGE_KEY, JSON.stringify(cards)); }
  function upsert(card) {
    const cards = load();
    const copy = { ...blankCard(card.name || 'Новый бренд'), ...card };
    copy.id = copy.id || slug(copy.name);
    const idx = cards.findIndex(x=>x.id===copy.id);
    if (idx >= 0) cards[idx] = copy; else cards.push(copy);
    save(cards); return copy;
  }
  function remove(id) { const cards = load().filter(x=>x.id!==id); save(cards); return cards; }
  root.LABBrands = { STORAGE_KEY, COMMON_EXCLUSIONS, load, save, upsert, remove, blankCard };
})(typeof globalThis !== 'undefined' ? globalThis : window);
