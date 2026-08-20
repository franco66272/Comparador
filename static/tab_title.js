(function () {
    const mensajes = [
        'TecnoRadar - Compará precios',
        'TecnoRadar - ¿Encontraste una oferta?',
        'TecnoRadar - ¡Mirá estos precios!',
        'TecnoRadar - ¿Bajó de precio?',
        'TecnoRadar - Buscá tecnología',
        'TecnoRadar - Compará y ahorrá',
        'TecnoRadar - Te estamos esperando',
        'TecnoRadar - ¿Qué estás buscando?',
    ];

    const dominios = {
        'Katech':'katech.com.ar','Quantum Hardstore':'quantumhardstore.com','Shop Gamer':'shopgamer.com.ar','Gaming City':'gamingcity.com.ar','Insumos Acuario':'insumosacuario.com.ar','Fullh4rd':'fullh4rd.com.ar','CompraGamer':'compragamer.com','Maximus':'maximus.com.ar','Gezatek':'gezatek.com.ar','MYM Computación':'mymcomputacion.com','XT-PC':'xt-pc.com.ar','Hardcore Computación':'hardcorecomputacion.com.ar','Integrados Argentinos':'integradosargentinos.com','Rocket Hard':'rockethard.com.ar','Hypergaming':'hypergaming.com.ar','Liontech Gaming':'liontech-gaming.com','710 Tech':'710tech.com.ar','Noxie Store':'noxiestore.com','Compufan Store':'compufanstore.com.ar','Netgaming':'netgaming.ar','Armytech':'armytech.com.ar','NG Technologies':'ngtechnologies.com.ar','Logg':'logg.com.ar','Megasoft Argentina':'megasoftargentina.com.ar','Mexx':'mexx.com.ar','Puerto Minero':'puertominero.com.ar','Backup Computación':'backupcomputacion.com','Venex':'venex.com.ar','Space Gamer':'spacegamer.com.ar','Portal Store':'portalstore.com.ar','Slot One':'slot-one.com.ar','Necxus':'necxus.com.ar','VRX':'vrx.com.ar','37Bytes':'37bytes.com.ar','Gamer Factory':'gamerfactory.com.ar',
        '37 Bytes':'37bytes.com.ar','Click Gaming':'clickgaming.com.ar','Dinobyte':'dinobyte.ar','GoldenTech Store':'goldentechstore.com.ar','HF Tecnologia':'hftecnologia.com.ar','Max Tecno':'maxtecno.com.ar','Portal Tech & Gaming':'portaltechgaming.com.ar','SCP Hardstore':'scphardstore.com','The Gamer Shop':'thegamershop.com.ar','Vertex Retail':'vertexretail.com.ar','WIZ TECH':'wiztech.com.ar'
    };

    const faltantes = [
        ['37 Bytes','37bytes.com.ar','37bytes_com_ar'],
        ['Click Gaming','clickgaming.com.ar','clickgaming_com_ar'],
        ['Dinobyte','dinobyte.ar','dinobyte_ar'],
        ['GoldenTech Store','goldentechstore.com.ar','goldentechstore_com_ar'],
        ['HF Tecnologia','hftecnologia.com.ar','hftecnologia_com_ar'],
        ['Max Tecno','maxtecno.com.ar','maxtecno_com_ar'],
        ['Portal Tech & Gaming','portaltechgaming.com.ar','portaltechgaming_com_ar'],
        ['SCP Hardstore','scphardstore.com','scphardstore_com'],
        ['The Gamer Shop','thegamershop.com.ar','thegamershop_com_ar'],
        ['Vertex Retail','vertexretail.com.ar','vertexretail_com_ar'],
        ['WIZ TECH','wiztech.com.ar','wiztech_com_ar']
    ];

    function aplicarLogo() {
        document.querySelectorAll('.brand-mark').forEach(function (elemento) {
            elemento.innerHTML = `
                <svg class="tecnoradar-logo-icon" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
                    <circle cx="24" cy="24" r="17" fill="none" stroke="#38bdf8" stroke-width="3" opacity="0.95"/>
                    <circle cx="24" cy="24" r="10" fill="none" stroke="#2563eb" stroke-width="3" opacity="0.95"/>
                    <circle cx="24" cy="24" r="3.5" fill="#22c55e"/>
                    <path d="M24 24 L39 11 A21 21 0 0 1 42 18 Z" fill="#38bdf8"/>
                    <path d="M24 24 L35 35" stroke="#2563eb" stroke-width="3" stroke-linecap="round"/>
                </svg>`;
            elemento.style.width = '36px';
            elemento.style.height = '36px';
            elemento.style.borderRadius = '0';
            elemento.style.background = 'transparent';
            elemento.style.fontSize = '0';
            elemento.style.display = 'inline-flex';
            elemento.style.flexShrink = '0';
        });
    }

    function cargarLogo(img, dominio) {
        const fuentes = [
            `https://www.${dominio}/favicon.ico`,
            `https://${dominio}/favicon.ico`,
            `https://icons.duckduckgo.com/ip3/${dominio}.ico`,
            `https://www.google.com/s2/favicons?domain=${encodeURIComponent(dominio)}&sz=128`
        ];
        let indice = 0;
        function siguiente() {
            if (indice >= fuentes.length) {
                img.style.display = 'none';
                const fallback = img.nextElementSibling;
                if (fallback) fallback.style.display = 'flex';
                return;
            }
            const src = fuentes[indice++];
            if (img.src === src) return siguiente();
            img.onerror = siguiente;
            img.src = src;
        }
        siguiente();
    }

    function corregirLogos() {
        document.querySelectorAll('.store-logo').forEach(function (img) {
            const nombre = (img.alt || '').replace(/^Logo\s+/i, '').trim();
            const dominio = dominios[nombre];
            if (dominio) cargarLogo(img, dominio);
        });
    }

    function agregarTiendasFaltantes() {
        const grid = document.querySelector('.store-grid-more');
        if (!grid) return;

        faltantes.forEach(function ([nombre, dominio, clave]) {
            const existe = Array.from(grid.querySelectorAll('.store-card')).some(function (card) {
                const titulo = card.querySelector('strong');
                return titulo && titulo.textContent.trim().toLowerCase() === nombre.toLowerCase();
            });
            if (existe) return;

            const card = document.createElement('a');
            card.className = 'store-card';
            card.href = `/?tienda=${encodeURIComponent(clave)}`;
            card.innerHTML = `
                <span class="store-logo-wrap">
                    <img class="store-logo" src="https://www.${dominio}/favicon.ico" alt="Logo ${nombre}" loading="lazy" referrerpolicy="no-referrer">
                    <span class="store-badge store-fallback" style="display:none">${nombre.charAt(0).toUpperCase()}</span>
                </span>
                <div><strong>${nombre}</strong><small>0 productos</small></div>
                <span class="store-arrow">→</span>`;
            grid.appendChild(card);
        });

        corregirLogos();
        const summary = document.querySelector('.stores-more summary');
        const count = document.querySelectorAll('.store-logo-strip .store-logo-card').length + document.querySelectorAll('.store-grid-more .store-card').length;
        if (summary) {
            const span = summary.querySelector('span');
            if (span) span.textContent = `· ${count} tiendas`;
        }
    }

    let indice = 0;
    let temporizador = null;

    function cambiarTitulo() {
        document.title = mensajes[indice];
        indice = (indice + 1) % mensajes.length;
    }

    function iniciarTituloDinamico() {
        aplicarLogo();
        agregarTiendasFaltantes();
        corregirLogos();
        cambiarTitulo();
        temporizador = window.setInterval(cambiarTitulo, 2200);

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                if (temporizador) {
                    clearInterval(temporizador);
                    temporizador = null;
                }
            } else if (!temporizador) {
                cambiarTitulo();
                temporizador = window.setInterval(cambiarTitulo, 2200);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', iniciarTituloDinamico, { once: true });
    } else {
        iniciarTituloDinamico();
    }
})();
