(function () {
  const domains = {
    "Katech":"katech.com.ar",
    "Quantum Hardstore":"quantumhardstore.com",
    "Shop Gamer":"shopgamer.com.ar",
    "Gaming City":"gamingcity.com.ar",
    "Insumos Acuario":"insumosacuario.com.ar",
    "Fullh4rd":"fullh4rd.com.ar",
    "CompraGamer":"compragamer.com",
    "Maximus":"maximus.com.ar",
    "Gezatek":"gezatek.com.ar",
    "MYM Computación":"mymcomputacion.com",
    "XT-PC":"xt-pc.com.ar",
    "Hardcore Computación":"hardcorecomputacion.com.ar",
    "Integrados Argentinos":"integradosargentinos.com",
    "Rocket Hard":"rockethard.com.ar",
    "Hypergaming":"hypergaming.com.ar",
    "Liontech Gaming":"liontech-gaming.com",
    "710 Tech":"710tech.com.ar",
    "Noxie Store":"noxiestore.com",
    "Compufan Store":"compufanstore.com.ar",
    "Netgaming":"netgaming.ar",
    "Armytech":"armytech.com.ar",
    "NG Technologies":"ngtechnologies.com.ar",
    "Logg":"logg.com.ar",
    "Megasoft Argentina":"megasoftargentina.com.ar",
    "Mexx":"mexx.com.ar",
    "Puerto Minero":"puertominero.com.ar",
    "Backup Computación":"backupcomputacion.com",
    "Venex":"venex.com.ar",
    "Space Gamer":"spacegamer.com.ar",
    "Portal Store":"portalstore.com.ar",
    "Slot One":"slot-one.com.ar",
    "Necxus":"necxus.com.ar",
    "VRX":"vrx.com.ar",
    "37Bytes":"37bytes.com.ar",
    "Gamer Factory":"gamerfactory.com.ar"
  };

  function setFallback(img, domain) {
    const sources = [
      `https://${domain}/favicon.ico`,
      `https://icons.duckduckgo.com/ip3/${domain}.ico`,
      `https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`
    ];
    let i = 0;
    function next() {
      if (i >= sources.length) return;
      const src = sources[i++];
      if (img.src === src) { next(); return; }
      img.onerror = next;
      img.src = src;
    }
    next();
  }

  function init() {
    document.querySelectorAll('.store-logo').forEach(img => {
      const name = (img.alt || '').replace(/^Logo\s+/i, '').trim();
      const domain = domains[name];
      if (!domain) return;
      setFallback(img, domain);
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
