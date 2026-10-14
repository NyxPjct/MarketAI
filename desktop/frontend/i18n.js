(() => {
  'use strict';

  const STORAGE_KEY = 'marketai-language';
  const SUPPORTED = {
    en: { label: 'English', locale: 'en-US' },
    'pt-BR': { label: 'Português (Brasil)', locale: 'pt-BR' },
    de: { label: 'Deutsch', locale: 'de-DE' },
    es: { label: 'Español', locale: 'es-ES' },
    fr: { label: 'Français', locale: 'fr-FR' }
  };

  // English is the canonical source language. The pt-BR column also works as
  // an alias layer for older dynamic strings that may still arrive in Portuguese.
  const C = {
    'MarketAI — Market Intelligence': ['MarketAI — Inteligência de mercado','MarketAI — Marktintelligenz','MarketAI — Inteligencia de mercado','MarketAI — Intelligence de marché'],
    'Market intelligence. No noise.': ['Inteligência de mercado. Sem ruído.','Marktintelligenz. Ohne Rauschen.','Inteligencia de mercado. Sin ruido.','Intelligence de marché. Sans bruit.'],
    'Pricing, margins, competition and monitoring in a direct interface for people who work with markets every day.': ['Preço, margem, concorrência e monitoramento em uma interface direta para quem trabalha com mercado todos os dias.','Preise, Margen, Wettbewerb und Monitoring in einer direkten Oberfläche für alle, die täglich mit Märkten arbeiten.','Precios, márgenes, competencia y monitoreo en una interfaz directa para quienes trabajan con mercados todos los días.','Prix, marges, concurrence et suivi dans une interface directe pour celles et ceux qui travaillent avec les marchés au quotidien.'],
    '100% FREE': ['100% GRATUITO','100% KOSTENLOS','100% GRATIS','100 % GRATUIT'],
    'OPEN SOURCE': ['OPEN SOURCE','OPEN SOURCE','OPEN SOURCE','OPEN SOURCE'],
    'REAL DATA': ['DADOS REAIS','ECHTE DATEN','DATOS REALES','DONNÉES RÉELLES'],
    'WELCOME': ['BEM-VINDO','WILLKOMMEN','BIENVENIDO','BIENVENUE'],
    'Sign in to MarketAI': ['Entrar no MarketAI','Bei MarketAI anmelden','Iniciar sesión en MarketAI','Se connecter à MarketAI'],
    'Access your account to continue.': ['Acesse sua conta para continuar.','Melde dich an, um fortzufahren.','Accede a tu cuenta para continuar.','Connectez-vous à votre compte pour continuer.'],
    'Email': ['E-mail','E-Mail','Correo electrónico','E-mail'],
    'Password': ['Senha','Passwort','Contraseña','Mot de passe'],
    'SIGN IN': ['ENTRAR','ANMELDEN','ENTRAR','SE CONNECTER'],
    'SIGNING IN…': ['ENTRANDO…','ANMELDUNG…','ENTRANDO…','CONNEXION…'],
    'Create a free account': ['Criar conta grátis','Kostenloses Konto erstellen','Crear cuenta gratis','Créer un compte gratuit'],
    'Free, open source, no subscription.': ['Gratuito, open source e sem assinatura.','Kostenlos, Open Source, ohne Abonnement.','Gratis, open source y sin suscripción.','Gratuit, open source et sans abonnement.'],
    'FREE ACCOUNT': ['CONTA GRATUITA','KOSTENLOSES KONTO','CUENTA GRATUITA','COMPTE GRATUIT'],
    'Create account': ['Criar conta','Konto erstellen','Crear cuenta','Créer un compte'],
    'All MarketAI features are unlocked. There is no paid plan.': ['Todos os recursos do MarketAI ficam liberados. Não existe plano pago.','Alle MarketAI-Funktionen sind freigeschaltet. Es gibt keinen kostenpflichtigen Tarif.','Todas las funciones de MarketAI están desbloqueadas. No existe un plan de pago.','Toutes les fonctionnalités de MarketAI sont débloquées. Il n’existe aucun forfait payant.'],
    'Name': ['Nome','Name','Nombre','Nom'],
    'CREATE ACCOUNT': ['CRIAR CONTA','KONTO ERSTELLEN','CREAR CUENTA','CRÉER LE COMPTE'],
    'CREATING…': ['CRIANDO…','WIRD ERSTELLT…','CREANDO…','CRÉATION…'],
    'I already have an account': ['Já tenho conta','Ich habe bereits ein Konto','Ya tengo una cuenta','J’ai déjà un compte'],
    'When you create an account, your data is linked only to your user.': ['Ao criar a conta, seus dados ficam vinculados somente ao seu usuário.','Beim Erstellen eines Kontos werden deine Daten nur deinem Benutzer zugeordnet.','Al crear la cuenta, tus datos quedan vinculados únicamente a tu usuario.','Lors de la création du compte, vos données sont associées uniquement à votre utilisateur.'],
    'pricing intelligence': ['inteligência de preços','Preisintelligenz','inteligencia de precios','intelligence tarifaire'],
    'New analysis': ['Nova análise','Neue Analyse','Nuevo análisis','Nouvelle analyse'],
    'Intelligence': ['Intelligence','Intelligence','Intelligence','Intelligence'],
    'Monitored': ['Monitorados','Beobachtet','Monitoreados','Surveillés'],
    'History': ['Histórico','Verlauf','Historial','Historique'],
    'My account': ['Minha conta','Mein Konto','Mi cuenta','Mon compte'],
    'Settings': ['Configurações','Einstellungen','Configuración','Paramètres'],
    'About': ['Sobre','Über','Acerca de','À propos'],
    'checking API…': ['verificando API…','API wird geprüft…','comprobando API…','vérification de l’API…'],
    'Update available': ['Atualização disponível','Update verfügbar','Actualización disponible','Mise à jour disponible'],
    'COMMERCIAL INTELLIGENCE': ['INTELIGÊNCIA COMERCIAL','MARKTINTELLIGENZ','INTELIGENCIA COMERCIAL','INTELLIGENCE COMMERCIALE'],
    'Know whether it is worth selling before you buy.': ['Descubra se vale a pena vender antes de comprar.','Erkenne vor dem Einkauf, ob sich der Verkauf lohnt.','Descubre si vale la pena vender antes de comprar.','Découvrez si la vente vaut le coup avant d’acheter.'],
    'Identify the product, compare marketplaces, convert currencies, simulate prices and see your real margin.': ['Identifique o produto, compare marketplaces, converta moedas, simule preços e veja sua margem real.','Produkt identifizieren, Marktplätze vergleichen, Währungen umrechnen, Preise simulieren und die reale Marge sehen.','Identifica el producto, compara marketplaces, convierte monedas, simula precios y consulta tu margen real.','Identifiez le produit, comparez les marketplaces, convertissez les devises, simulez les prix et visualisez votre marge réelle.'],
    'LIVE MARKET · Brazil + International': ['LIVE MARKET · Brasil + Internacional','LIVE MARKET · Brasilien + International','LIVE MARKET · Brasil + Internacional','LIVE MARKET · Brésil + International'],
    'Product': ['Produto','Produkt','Producto','Produit'],
    'name + image': ['nome + imagem','Name + Bild','nombre + imagen','nom + image'],
    'Product name': ['Nome do produto','Produktname','Nombre del producto','Nom du produit'],
    'Variant / size / version': ['Variante / tamanho / versão','Variante / Größe / Version','Variante / tamaño / versión','Variante / taille / version'],
    'highly recommended': ['muito recomendado','sehr empfohlen','muy recomendado','fortement recommandé'],
    'The more exact the variant, the lower the risk of comparing different products.': ['Quanto mais exata a variante, menor o risco de comparar produtos diferentes.','Je genauer die Variante, desto geringer das Risiko, unterschiedliche Produkte zu vergleichen.','Cuanto más exacta sea la variante, menor será el riesgo de comparar productos diferentes.','Plus la variante est précise, plus le risque de comparer des produits différents est faible.'],
    'optional': ['opcional','optional','opcional','facultatif'],
    'Comparison mode': ['Modo de comparação','Vergleichsmodus','Modo de comparación','Mode de comparaison'],
    'Strict — recommended': ['Estrito — recomendado','Streng — empfohlen','Estricto — recomendado','Strict — recommandé'],
    'Balanced': ['Balanceado','Ausgewogen','Equilibrado','Équilibré'],
    'Strict rejects kits, testers, decants, different volume/capacity and incompatible variants.': ['Estrito rejeita kit, tester, decant, volume/capacidade diferente e variantes incompatíveis.','Streng lehnt Sets, Tester, Decants, abweichende Volumen/Kapazitäten und inkompatible Varianten ab.','Estricto rechaza kits, testers, decants, volúmenes/capacidades diferentes y variantes incompatibles.','Le mode strict rejette les kits, testers, décants, volumes/capacités différents et variantes incompatibles.'],
    'Country of origin': ['País de origem','Herkunftsland','País de origen','Pays d’origine'],
    'Destination country': ['País de venda','Zielland','País de venta','Pays de vente'],
    'China': ['China','China','China','Chine'],
    'Brazil': ['Brasil','Brasilien','Brasil','Brésil'],
    'United States': ['Estados Unidos','Vereinigte Staaten','Estados Unidos','États-Unis'],
    'France': ['França','Frankreich','Francia','France'],
    'Japan': ['Japão','Japan','Japón','Japon'],
    'South Korea': ['Coreia do Sul','Südkorea','Corea del Sur','Corée du Sud'],
    'Germany': ['Alemanha','Deutschland','Alemania','Allemagne'],
    'United Kingdom': ['Reino Unido','Vereinigtes Königreich','Reino Unido','Royaume-Uni'],
    'Mexico': ['México','Mexiko','México','Mexique'],
    'Argentina': ['Argentina','Argentinien','Argentina','Argentine'],
    'Canada': ['Canadá','Kanada','Canadá','Canada'],
    'Add product photo': ['Adicionar foto do produto','Produktfoto hinzufügen','Añadir foto del producto','Ajouter une photo du produit'],
    'AI uses the image to assist identification': ['A IA usa a imagem para auxiliar a identificação','KI verwendet das Bild zur Unterstützung der Identifikation','La IA usa la imagen para ayudar a identificar el producto','L’IA utilise l’image pour faciliter l’identification'],
    'Costs': ['Custos','Kosten','Costes','Coûts'],
    'purchase + logistics': ['compra + logística','Einkauf + Logistik','compra + logística','achat + logistique'],
    'Purchase cost': ['Custo de compra','Einkaufskosten','Coste de compra','Coût d’achat'],
    'Currency': ['Moeda','Währung','Moneda','Devise'],
    'Brazilian real': ['Real','Real','Real','Réal brésilien'],
    'Dollar': ['Dólar','Dollar','Dólar','Dollar'],
    'Yuan': ['Yuan','Yuan','Yuan','Yuan'],
    'Euro': ['Euro','Euro','Euro','Euro'],
    'Pound sterling': ['Libra','Pfund','Libra esterlina','Livre sterling'],
    'Yen': ['Iene','Yen','Yen','Yen'],
    'Canadian dollar': ['Dólar canadense','Kanadischer Dollar','Dólar canadiense','Dollar canadien'],
    'Mexican peso': ['Peso mexicano','Mexikanischer Peso','Peso mexicano','Peso mexicain'],
    'Argentine peso': ['Peso argentino','Argentinischer Peso','Peso argentino','Peso argentin'],
    'Won': ['Won','Won','Won','Won'],
    'Quantity': ['Quantidade','Menge','Cantidad','Quantité'],
    'Total freight': ['Frete total','Gesamtfracht','Flete total','Fret total'],
    'Total import / customs clearance': ['Importação / desembaraço total','Import / Zollabfertigung gesamt','Importación / despacho aduanero total','Importation / dédouanement total'],
    'Packaging per unit': ['Embalagem por unidade','Verpackung pro Einheit','Embalaje por unidad','Emballage par unité'],
    'Other costs per unit': ['Outros custos por unidade','Sonstige Kosten pro Einheit','Otros costes por unidad','Autres coûts par unité'],
    'Domestic cost for comparison': ['Custo nacional para comparar','Inlandskosten zum Vergleich','Coste nacional para comparar','Coût national à comparer'],
    'Supplier': ['Fornecedor','Lieferant','Proveedor','Fournisseur'],
    'Sales': ['Venda','Verkauf','Venta','Vente'],
    'fees + margin': ['taxas + margem','Gebühren + Marge','comisiones + margen','frais + marge'],
    'Marketplace %': ['Marketplace %','Marketplace %','Marketplace %','Marketplace %'],
    'Taxes %': ['Impostos %','Steuern %','Impuestos %','Taxes %'],
    'Advertising %': ['Publicidade %','Werbung %','Publicidad %','Publicité %'],
    'Desired margin %': ['Margem desejada %','Gewünschte Marge %','Margen deseado %','Marge souhaitée %'],
    'ANALYZE PRODUCT': ['ANALISAR PRODUTO','PRODUKT ANALYSIEREN','ANALIZAR PRODUCTO','ANALYSER LE PRODUIT'],
    'Analyzing market…': ['Analisando mercado…','Markt wird analysiert…','Analizando mercado…','Analyse du marché…'],
    'Identifying the product and cross-checking references.': ['Identificando o produto e cruzando referências.','Produkt wird identifiziert und Referenzen werden abgeglichen.','Identificando el producto y cruzando referencias.','Identification du produit et recoupement des références.'],
    'New analysis ←': ['← Nova análise','← Neue Analyse','← Nuevo análisis','← Nouvelle analyse'],
    'Monitor ★': ['★ Monitorar','★ Beobachten','★ Monitorear','★ Surveiller'],
    'Export CSV': ['Exportar CSV','CSV exportieren','Exportar CSV','Exporter CSV'],
    'Print / PDF': ['Imprimir / PDF','Drucken / PDF','Imprimir / PDF','Imprimer / PDF'],
    'IDENTIFIED PRODUCT': ['PRODUTO IDENTIFICADO','IDENTIFIZIERTES PRODUKT','PRODUCTO IDENTIFICADO','PRODUIT IDENTIFIÉ'],
    'Confidence': ['Confiança','Konfidenz','Confianza','Confiance'],
    'OPPORTUNITY INDEX': ['ÍNDICE DE OPORTUNIDADE','CHANCENINDEX','ÍNDICE DE OPORTUNIDAD','INDICE D’OPPORTUNITÉ'],
    'DATA QUALITY': ['QUALIDADE DOS DADOS','DATENQUALITÄT','CALIDAD DE DATOS','QUALITÉ DES DONNÉES'],
    'Market price': ['Preço de mercado','Marktpreis','Precio de mercado','Prix du marché'],
    'median of compatible listings': ['mediana dos anúncios compatíveis','Median kompatibler Angebote','mediana de anuncios compatibles','médiane des annonces compatibles'],
    'Recommended price': ['Preço recomendado','Empfohlener Preis','Precio recomendado','Prix recommandé'],
    'only with reliable market data': ['somente com mercado confiável','nur bei zuverlässigen Marktdaten','solo con mercado fiable','uniquement avec un marché fiable'],
    'Estimated profit': ['Lucro estimado','Geschätzter Gewinn','Beneficio estimado','Bénéfice estimé'],
    'True cost / unit': ['Custo real/unid.','Reale Kosten / Einheit','Coste real / unidad','Coût réel / unité'],
    'AI DECISION': ['DECISÃO DA IA','KI-ENTSCHEIDUNG','DECISIÓN DE IA','DÉCISION DE L’IA'],
    'Why it makes sense': ['Por que faz sentido','Warum es sinnvoll ist','Por qué tiene sentido','Pourquoi cela a du sens'],
    'Points of attention': ['Pontos de atenção','Wichtige Punkte','Puntos de atención','Points d’attention'],
    'Pricing strategies': ['Estratégias de preço','Preisstrategien','Estrategias de precio','Stratégies de prix'],
    '4 scenarios': ['4 cenários','4 Szenarien','4 escenarios','4 scénarios'],
    'Exchange rate used': ['Cotação usada','Verwendeter Wechselkurs','Tipo de cambio usado','Taux de change utilisé'],
    'Price simulator': ['Simulador de preço','Preissimulator','Simulador de precio','Simulateur de prix'],
    'Drag to see the margin change instantly.': ['Arraste e veja a margem mudar na hora.','Ziehen und die Margenänderung sofort sehen.','Arrastra y observa cómo cambia el margen al instante.','Faites glisser pour voir la marge changer instantanément.'],
    'Your price': ['Seu preço','Dein Preis','Tu precio','Votre prix'],
    'Net profit': ['Lucro líquido','Nettogewinn','Beneficio neto','Bénéfice net'],
    'Margin': ['Margem','Marge','Margen','Marge'],
    'ROI on cost': ['ROI sobre custo','ROI auf Kosten','ROI sobre coste','ROI sur coût'],
    'Competitiveness': ['Competitividade','Wettbewerbsfähigkeit','Competitividad','Compétitivité'],
    'Domestic vs imported': ['Nacional x importado','Inland vs. Import','Nacional vs importado','National vs importé'],
    'Comparison using the domestic cost provided.': ['Comparação usando o custo nacional informado.','Vergleich anhand der angegebenen Inlandskosten.','Comparación usando el coste nacional indicado.','Comparaison avec le coût national indiqué.'],
    'Buy domestic': ['Comprar nacional','Inländisch kaufen','Comprar nacional','Acheter national'],
    'Landed import cost': ['Custo importado posto','Importkosten geliefert','Coste importado puesto','Coût importé rendu'],
    'Best option': ['Melhor opção','Beste Option','Mejor opción','Meilleure option'],
    'Marketplace comparison': ['Comparação por marketplace','Marketplace-Vergleich','Comparación por marketplace','Comparaison par marketplace'],
    'See where the market is cheaper or more expensive.': ['Veja onde o mercado está mais barato ou mais caro.','Sieh, wo der Markt günstiger oder teurer ist.','Mira dónde el mercado es más barato o más caro.','Voyez où le marché est moins cher ou plus cher.'],
    'Cost composition': ['Composição do custo','Kostenzusammensetzung','Composición del coste','Composition du coût'],
    'Compatible listings': ['Anúncios compatíveis','Kompatible Angebote','Anuncios compatibles','Annonces compatibles'],
    'Match': ['Match','Match','Match','Match'],
    'Source': ['Fonte','Quelle','Fuente','Source'],
    'Store / seller': ['Loja / vendedor','Shop / Verkäufer','Tienda / vendedor','Boutique / vendeur'],
    'Listing': ['Anúncio','Angebot','Anuncio','Annonce'],
    'Detected variant': ['Variante detectada','Erkannte Variante','Variante detectada','Variante détectée'],
    'Price': ['Preço','Preis','Precio','Prix'],
    'Discarded listings': ['Anúncios descartados','Verworfene Angebote','Anuncios descartados','Annonces écartées'],
    'They are shown here so you can audit why they were excluded from the calculation.': ['Estão aqui para você auditar por que não entraram no cálculo.','Sie werden hier angezeigt, damit du prüfen kannst, warum sie nicht in die Berechnung eingegangen sind.','Se muestran aquí para que puedas auditar por qué se excluyeron del cálculo.','Ils sont affichés ici afin que vous puissiez vérifier pourquoi ils ont été exclus du calcul.'],
    'Rejection reason': ['Motivo do descarte','Ablehnungsgrund','Motivo del descarte','Motif du rejet'],
    'Important': ['Importante','Wichtig','Importante','Important'],
    'MarketAI Community does not create fictitious market prices. If there are fewer than 3 compatible real listings, or variants are mixed, it only shows the minimum price calculated from your costs and blocks the market recommendation. Listing compatibility does not prove physical authenticity. NCM and taxation must be validated with an accountant/customs professional.': ['O MarketAI v1.0.2 Community não cria preços de mercado fictícios. Se não houver pelo menos 3 anúncios reais compatíveis, ou se as variantes estiverem misturadas, ele mostra apenas o preço mínimo calculado pelos seus custos e bloqueia a recomendação de mercado. Compatibilidade de anúncio não comprova autenticidade física do produto. NCM e tributação devem ser validados com contador/despachante.','MarketAI Community erstellt keine fiktiven Marktpreise. Gibt es weniger als 3 kompatible reale Angebote oder werden Varianten gemischt, wird nur der aus deinen Kosten berechnete Mindestpreis angezeigt und die Marktempfehlung gesperrt. Angebotskompatibilität beweist keine physische Echtheit. NCM und Steuern müssen mit Fachleuten geprüft werden.','MarketAI Community no crea precios de mercado ficticios. Si hay menos de 3 anuncios reales compatibles o se mezclan variantes, solo muestra el precio mínimo calculado a partir de tus costes y bloquea la recomendación de mercado. La compatibilidad del anuncio no demuestra la autenticidad física. El NCM y la tributación deben validarse con profesionales.','MarketAI Community ne crée pas de prix de marché fictifs. S’il y a moins de 3 annonces réelles compatibles ou si des variantes sont mélangées, seul le prix minimum calculé à partir de vos coûts est affiché et la recommandation de marché est bloquée. La compatibilité d’une annonce ne prouve pas l’authenticité physique. Le NCM et la fiscalité doivent être validés par des professionnels.'],
    'Your commercial command center.': ['Seu centro de comando comercial.','Deine kommerzielle Kommandozentrale.','Tu centro de mando comercial.','Votre centre de commande commercial.'],
    'Real Radar, Sentinel, alerts, forecasting, Profit Engine and Copilot — all based on data collected by your account.': ['Radar real, Sentinel, alertas, previsão, Profit Engine e Copilot — todos baseados nos dados coletados pela sua conta.','Echtes Radar, Sentinel, Warnungen, Prognosen, Profit Engine und Copilot — alles auf Basis der von deinem Konto erfassten Daten.','Radar real, Sentinel, alertas, previsión, Profit Engine y Copilot — todo basado en los datos recopilados por tu cuenta.','Radar réel, Sentinel, alertes, prévisions, Profit Engine et Copilot — tous basés sur les données collectées par votre compte.'],
    'REFRESH CENTER': ['ATUALIZAR CENTRAL','ZENTRALE AKTUALISIEREN','ACTUALIZAR CENTRO','ACTUALISER LE CENTRE'],
    'Opportunities': ['Oportunidades','Chancen','Oportunidades','Opportunités'],
    'Refresh to load.': ['Atualize para carregar.','Zum Laden aktualisieren.','Actualiza para cargar.','Actualisez pour charger.'],
    'Critical alerts': ['Alertas críticos','Kritische Warnungen','Alertas críticas','Alertes critiques'],
    'Ask your data': ['Pergunte aos seus dados','Frag deine Daten','Pregunta a tus datos','Interrogez vos données'],
    'ASK': ['PERGUNTAR','FRAGEN','PREGUNTAR','DEMANDER'],
    'Copilot does not invent data. If there are no snapshots, it tells you.': ['O Copilot não inventa dados. Se não houver snapshots, ele avisa.','Copilot erfindet keine Daten. Wenn keine Snapshots vorhanden sind, sagt er es dir.','Copilot no inventa datos. Si no hay snapshots, te lo indica.','Copilot n’invente pas de données. S’il n’y a pas de snapshots, il vous le signale.'],
    'Quick net profit': ['Lucro líquido rápido','Schneller Nettogewinn','Beneficio neto rápido','Bénéfice net rapide'],
    'Cost': ['Custo','Kosten','Coste','Coût'],
    'Payment %': ['Pagamento %','Zahlung %','Pago %','Paiement %'],
    'CALCULATE': ['CALCULAR','BERECHNEN','CALCULAR','CALCULER'],
    'Monitored products': ['Produtos monitorados','Beobachtete Produkte','Productos monitoreados','Produits surveillés'],
    'Stored locally in this browser. You can reanalyze them whenever you want.': ['Salvos localmente neste navegador. Você pode reanalisar quando quiser.','Lokal in diesem Browser gespeichert. Du kannst sie jederzeit neu analysieren.','Guardados localmente en este navegador. Puedes volver a analizarlos cuando quieras.','Enregistrés localement dans ce navigateur. Vous pouvez les réanalyser quand vous le souhaitez.'],
    'Clear': ['Limpar','Leeren','Limpiar','Effacer'],
    'Local history': ['Histórico local','Lokaler Verlauf','Historial local','Historique local'],
    'Analyses saved in this browser.': ['Análises salvas neste navegador.','In diesem Browser gespeicherte Analysen.','Análisis guardados en este navegador.','Analyses enregistrées dans ce navigateur.'],
    'Analysis evolution': ['Evolução das análises','Analyseentwicklung','Evolución de los análisis','Évolution des analyses'],
    'Recommended price and median from recent records.': ['Preço recomendado e mediana dos registros recentes.','Empfohlener Preis und Median der letzten Datensätze.','Precio recomendado y mediana de los registros recientes.','Prix recommandé et médiane des enregistrements récents.'],
    'YOUR ACCOUNT': ['SUA CONTA','DEIN KONTO','TU CUENTA','VOTRE COMPTE'],
    'Access': ['Acesso','Zugang','Acceso','Accès'],
    'FREE': ['GRÁTIS','KOSTENLOS','GRATIS','GRATUIT'],
    'Analyses': ['Análises','Analysen','Análisis','Analyses'],
    'UNLIMITED': ['ILIMITADAS','UNBEGRENZT','ILIMITADOS','ILLIMITÉES'],
    'Status': ['Status','Status','Estado','Statut'],
    'ACTIVE': ['ATIVO','AKTIV','ACTIVO','ACTIF'],
    'Refresh account': ['Atualizar conta','Konto aktualisieren','Actualizar cuenta','Actualiser le compte'],
    'Sign out': ['Sair','Abmelden','Salir','Se déconnecter'],
    'No paid plans, no monthly quota and no feature locks.': ['Sem planos pagos, sem cota mensal e sem bloqueio de recursos.','Keine kostenpflichtigen Tarife, keine Monatsquote und keine gesperrten Funktionen.','Sin planes de pago, sin cuota mensual y sin funciones bloqueadas.','Aucun forfait payant, aucun quota mensuel et aucune fonctionnalité bloquée.'],
    'All modules': ['Todos os módulos','Alle Module','Todos los módulos','Tous les modules'],
    'Individual account': ['Conta individual','Individuelles Konto','Cuenta individual','Compte individuel'],
    'Each person accesses their own data, history and monitored products.': ['Cada pessoa acessa os próprios dados, histórico e monitoramentos.','Jede Person greift auf ihre eigenen Daten, ihren Verlauf und ihre Überwachungen zu.','Cada persona accede a sus propios datos, historial y monitoreos.','Chaque personne accède à ses propres données, historique et suivis.'],
    'Professional use': ['Uso profissional','Professionelle Nutzung','Uso profesional','Usage professionnel'],
    'Use it at work and every day without a subscription.': ['Pode ser usado no trabalho e no dia a dia sem assinatura.','Im Beruf und Alltag ohne Abonnement nutzbar.','Puede usarse en el trabajo y en el día a día sin suscripción.','Utilisable au travail et au quotidien sans abonnement.'],
    'Open source': ['Código aberto','Open Source','Código abierto','Open source'],
    'The project and community can evolve together.': ['O projeto e a comunidade podem evoluir juntos.','Projekt und Community können sich gemeinsam weiterentwickeln.','El proyecto y la comunidad pueden evolucionar juntos.','Le projet et la communauté peuvent évoluer ensemble.'],
    'DEVICES': ['DISPOSITIVOS','GERÄTE','DISPOSITIVOS','APPAREILS'],
    'Your computers': ['Seus computadores','Deine Computer','Tus ordenadores','Vos ordinateurs'],
    'Devices linked to your account.': ['Dispositivos vinculados à sua conta.','Mit deinem Konto verknüpfte Geräte.','Dispositivos vinculados a tu cuenta.','Appareils liés à votre compte.'],
    'Loading devices…': ['Carregando dispositivos…','Geräte werden geladen…','Cargando dispositivos…','Chargement des appareils…'],
    'Centralized services': ['Serviços centralizados','Zentralisierte Dienste','Servicios centralizados','Services centralisés'],
    'In the Community edition, centralized integrations can stay in MarketAI Cloud. You do not need to expose sensitive API keys in the app.': ['Na edição Community, as integrações centralizadas podem ficar no MarketAI Cloud. Você não precisa expor chaves sensíveis no aplicativo.','In der Community Edition können zentralisierte Integrationen in der MarketAI Cloud verbleiben. Sensible API-Schlüssel müssen nicht in der App offengelegt werden.','En la edición Community, las integraciones centralizadas pueden permanecer en MarketAI Cloud. No necesitas exponer claves sensibles en la aplicación.','Dans l’édition Community, les intégrations centralisées peuvent rester dans MarketAI Cloud. Vous n’avez pas besoin d’exposer de clés sensibles dans l’application.'],
    'Your account and devices can be managed in': ['Sua conta e seus dispositivos podem ser gerenciados em','Dein Konto und deine Geräte können verwaltet werden unter','Tu cuenta y tus dispositivos pueden gestionarse en','Votre compte et vos appareils peuvent être gérés dans'],
    'DEFAULTS': ['PADRÕES','STANDARDWERTE','PREDETERMINADOS','VALEURS PAR DÉFAUT'],
    'Preferences': ['Preferências','Einstellungen','Preferencias','Préférences'],
    'Values used to start new analyses.': ['Valores usados para iniciar novas análises.','Werte, die für neue Analysen verwendet werden.','Valores usados al iniciar nuevos análisis.','Valeurs utilisées pour démarrer de nouvelles analyses.'],
    'Purchase currency': ['Moeda de compra','Einkaufswährung','Moneda de compra','Devise d’achat'],
    'Margin %': ['Margem %','Marge %','Margen %','Marge %'],
    'SAVE PREFERENCES': ['SALVAR PREFERÊNCIAS','EINSTELLUNGEN SPEICHERN','GUARDAR PREFERENCIAS','ENREGISTRER LES PRÉFÉRENCES'],
    'LOCAL DATA': ['DADOS LOCAIS','LOKALE DATEN','DATOS LOCALES','DONNÉES LOCALES'],
    'Backup and diagnostics': ['Backup e diagnóstico','Backup und Diagnose','Copia de seguridad y diagnóstico','Sauvegarde et diagnostic'],
    'History and monitored products stay on this computer.': ['Histórico e monitorados ficam neste computador.','Verlauf und überwachte Produkte bleiben auf diesem Computer.','El historial y los productos monitoreados permanecen en este ordenador.','L’historique et les produits surveillés restent sur cet ordinateur.'],
    'Export backup': ['Exportar backup','Backup exportieren','Exportar copia','Exporter la sauvegarde'],
    'Import backup': ['Importar backup','Backup importieren','Importar copia','Importer la sauvegarde'],
    'Export diagnostics': ['Exportar diagnóstico','Diagnose exportieren','Exportar diagnóstico','Exporter le diagnostic'],
    'Open data folder': ['Abrir pasta de dados','Datenordner öffnen','Abrir carpeta de datos','Ouvrir le dossier de données'],
    'COMMUNITY OPEN SOURCE': ['COMMUNITY OPEN SOURCE','COMMUNITY OPEN SOURCE','COMMUNITY OPEN SOURCE','COMMUNITY OPEN SOURCE'],
    'Market intelligence for analyzing price, margin and data quality before making a decision.': ['Inteligência de mercado para analisar preço, margem e qualidade dos dados antes de tomar decisão.','Marktintelligenz zur Analyse von Preis, Marge und Datenqualität vor einer Entscheidung.','Inteligencia de mercado para analizar precio, margen y calidad de datos antes de decidir.','Intelligence de marché pour analyser le prix, la marge et la qualité des données avant de décider.'],
    'MarketAI commitments': ['Compromissos do MarketAI','MarketAI-Versprechen','Compromisos de MarketAI','Engagements de MarketAI'],
    'Does not fabricate market prices when sources do not respond.': ['Não fabrica preços de mercado quando as fontes não respondem.','Erfindet keine Marktpreise, wenn Quellen nicht antworten.','No inventa precios de mercado cuando las fuentes no responden.','N’invente pas de prix de marché lorsque les sources ne répondent pas.'],
    'Blocks recommendations when the sample is insufficient or the variant is ambiguous.': ['Bloqueia recomendação com amostra insuficiente ou variante ambígua.','Blockiert Empfehlungen bei unzureichender Stichprobe oder mehrdeutiger Variante.','Bloquea recomendaciones con muestra insuficiente o variante ambigua.','Bloque les recommandations lorsque l’échantillon est insuffisant ou la variante ambiguë.'],
    'Shows the listings used and discarded for auditing.': ['Mostra os anúncios usados e descartados para auditoria.','Zeigt verwendete und verworfene Angebote zur Prüfung.','Muestra los anuncios usados y descartados para auditoría.','Affiche les annonces utilisées et écartées pour audit.'],
    'Does not put core features behind a paywall.': ['Não coloca os recursos principais atrás de paywall.','Versteckt Kernfunktionen nicht hinter einer Paywall.','No pone las funciones principales tras un paywall.','Ne place pas les fonctions principales derrière un paywall.'],
    'Session tokens are protected on Windows and marketplace keys stay only in MarketAI Cloud.': ['Tokens de sessão são protegidos no Windows e as chaves dos marketplaces ficam apenas no MarketAI Cloud.','Sitzungstokens sind unter Windows geschützt und Marketplace-Schlüssel bleiben nur in der MarketAI Cloud.','Los tokens de sesión están protegidos en Windows y las claves de marketplaces permanecen solo en MarketAI Cloud.','Les jetons de session sont protégés sous Windows et les clés des marketplaces restent uniquement dans MarketAI Cloud.'],
    'Important limitations': ['Limites importantes','Wichtige Einschränkungen','Limitaciones importantes','Limites importantes'],
    'Prices change, APIs may limit results and textual compatibility does not prove physical authenticity. NCM, taxes, customs clearance and accounting decisions must be validated by responsible professionals.': ['Preços mudam, APIs podem limitar resultados e compatibilidade textual não comprova autenticidade física de um item. NCM, impostos, desembaraço e decisões contábeis devem ser validados com profissionais responsáveis.','Preise ändern sich, APIs können Ergebnisse begrenzen und textuelle Kompatibilität beweist keine Echtheit. NCM, Steuern, Zollabfertigung und Buchhaltungsentscheidungen müssen von Fachleuten geprüft werden.','Los precios cambian, las APIs pueden limitar resultados y la compatibilidad textual no demuestra autenticidad física. NCM, impuestos, aduanas y decisiones contables deben validarse con profesionales.','Les prix changent, les API peuvent limiter les résultats et la compatibilité textuelle ne prouve pas l’authenticité physique. NCM, taxes, dédouanement et décisions comptables doivent être validés par des professionnels.'],
    'Documents': ['Documentos','Dokumente','Documentos','Documents'],
    'Terms of Use': ['Termos de Uso','Nutzungsbedingungen','Términos de uso','Conditions d’utilisation'],
    'Privacy': ['Privacidade','Datenschutz','Privacidad','Confidentialité'],
    'Third parties': ['Terceiros','Drittanbieter','Terceros','Tiers'],
    'Everything is ready.': ['Tudo certo.','Alles bereit.','Todo listo.','Tout est prêt.'],
    'Operation completed.': ['Operação concluída.','Vorgang abgeschlossen.','Operación completada.','Opération terminée.'],
    'CONTINUE': ['CONTINUAR','WEITER','CONTINUAR','CONTINUER'],
    'ACCOUNT CREATED': ['CONTA CRIADA','KONTO ERSTELLT','CUENTA CREADA','COMPTE CRÉÉ'],
    'Welcome to MarketAI.': ['Bem-vindo ao MarketAI.','Willkommen bei MarketAI.','Bienvenido a MarketAI.','Bienvenue sur MarketAI.'],
    'ENTER MARKETAI': ['ENTRAR NO MARKETAI','MARKETAI ÖFFNEN','ENTRAR A MARKETAI','ENTRER DANS MARKETAI'],
    'Language': ['Idioma','Sprache','Idioma','Langue'],
    'Interface language': ['Idioma da interface','Sprache der Oberfläche','Idioma de la interfaz','Langue de l’interface'],
    'Choose the language used across the entire app.': ['Escolha o idioma usado em todo o aplicativo.','Wähle die Sprache für die gesamte App.','Elige el idioma usado en toda la aplicación.','Choisissez la langue utilisée dans toute l’application.'],
    'LANGUAGE': ['IDIOMA','SPRACHE','IDIOMA','LANGUE'],
    'English is the default language. Your choice is saved on this device.': ['Inglês é o idioma padrão. Sua escolha fica salva neste dispositivo.','Englisch ist die Standardsprache. Deine Auswahl wird auf diesem Gerät gespeichert.','El inglés es el idioma predeterminado. Tu elección se guarda en este dispositivo.','L’anglais est la langue par défaut. Votre choix est enregistré sur cet appareil.'],

    // Common dynamic strings / statuses.
    'Public ML': ['ML público','Öffentliches ML','ML público','ML public'],
    'AI vision': ['visão IA','KI-Vision','visión IA','vision IA'],
    'API offline': ['API offline','API offline','API sin conexión','API hors ligne'],
    'Identifying product, variant and attributes.': ['Identificando produto, variante e atributos.','Produkt, Variante und Attribute werden identifiziert.','Identificando producto, variante y atributos.','Identification du produit, de la variante et des attributs.'],
    'Querying only available real sources.': ['Consultando apenas fontes reais disponíveis.','Es werden nur verfügbare reale Quellen abgefragt.','Consultando solo fuentes reales disponibles.','Consultation uniquement des sources réelles disponibles.'],
    'Rejecting kits, testers, decants and incompatible variants.': ['Rejeitando kit, tester, decant e variantes incompatíveis.','Sets, Tester, Decants und inkompatible Varianten werden abgelehnt.','Rechazando kits, testers, decants y variantes incompatibles.','Rejet des kits, testers, décants et variantes incompatibles.'],
    'Validating volume, capacity, power and outliers.': ['Validando volume, capacidade, potência e outliers.','Volumen, Kapazität, Leistung und Ausreißer werden geprüft.','Validando volumen, capacidad, potencia y outliers.','Validation du volume, de la capacité, de la puissance et des valeurs aberrantes.'],
    'Calculating price only if the sample is reliable.': ['Calculando preço somente se a amostra for confiável.','Preis wird nur bei zuverlässiger Stichprobe berechnet.','Calculando el precio solo si la muestra es fiable.','Calcul du prix uniquement si l’échantillon est fiable.'],
    'Sign in to your MarketAI account to analyze products.': ['Entre na sua conta MarketAI para analisar produtos.','Melde dich bei MarketAI an, um Produkte zu analysieren.','Inicia sesión en tu cuenta MarketAI para analizar productos.','Connectez-vous à votre compte MarketAI pour analyser des produits.'],
    'This computer is not linked to your account yet. Sign out and sign in again to reactivate it.': ['Este computador ainda não está vinculado à sua conta. Saia e entre novamente para reativá-lo.','Dieser Computer ist noch nicht mit deinem Konto verknüpft. Melde dich ab und erneut an.','Este ordenador todavía no está vinculado a tu cuenta. Cierra sesión y vuelve a entrar para reactivarlo.','Cet ordinateur n’est pas encore lié à votre compte. Déconnectez-vous puis reconnectez-vous pour le réactiver.'],
    'The server is temporarily rate-limiting requests. Try again in a moment.': ['O servidor está temporariamente limitando requisições. Tente novamente em instantes.','Der Server begrenzt Anfragen vorübergehend. Versuche es gleich erneut.','El servidor está limitando temporalmente las solicitudes. Inténtalo de nuevo en un momento.','Le serveur limite temporairement les requêtes. Réessayez dans un instant.'],
    'Could not complete the analysis.': ['Não foi possível concluir a análise.','Analyse konnte nicht abgeschlossen werden.','No se pudo completar el análisis.','Impossible de terminer l’analyse.'],
    'I could not complete the analysis.': ['Não consegui concluir a análise.','Ich konnte die Analyse nicht abschließen.','No pude completar el análisis.','Je n’ai pas pu terminer l’analyse.'],
    'not identified in title': ['não identificada no título','im Titel nicht identifiziert','no identificada en el título','non identifiée dans le titre'],
    'APPROVED FOR PRICING': ['APROVADO PARA CÁLCULO','FÜR PREISBERECHNUNG FREIGEGEBEN','APROBADO PARA CÁLCULO','APPROUVÉ POUR LE CALCUL'],
    'AMBIGUOUS VARIANT': ['VARIANTE AMBÍGUA','MEHRDEUTIGE VARIANTE','VARIANTE AMBIGUA','VARIANTE AMBIGUË'],
    'NO RELIABLE PRICE': ['SEM PREÇO CONFIÁVEL','KEIN ZUVERLÄSSIGER PREIS','SIN PRECIO FIABLE','AUCUN PRIX FIABLE'],
    'not configured': ['não configurado','nicht konfiguriert','no configurado','non configuré'],
    'authentication required': ['autenticação necessária','Authentifizierung erforderlich','autenticación necesaria','authentification requise'],
    'request limit': ['limite de requisições','Anfragelimit','límite de solicitudes','limite de requêtes'],
    'network error': ['erro de rede','Netzwerkfehler','error de red','erreur réseau'],
    'source unavailable': ['fonte indisponível','Quelle nicht verfügbar','fuente no disponible','source indisponible'],
    'fallback': ['contingência','Fallback','contingencia','secours'],
    'unavailable': ['indisponível','nicht verfügbar','no disponible','indisponible'],
    'Basic identification': ['Identificação básica','Grundidentifikation','Identificación básica','Identification de base'],
    'No additional codes provided': ['Sem códigos adicionais informados','Keine zusätzlichen Codes angegeben','No se proporcionaron códigos adicionales','Aucun code supplémentaire fourni'],
    'Score blocked until reliable market data exists': ['Score bloqueado até existir mercado confiável','Score gesperrt, bis zuverlässige Marktdaten vorliegen','Score bloqueado hasta disponer de mercado fiable','Score bloqué jusqu’à la disponibilité de données de marché fiables'],
    'No median': ['Sem mediana','Kein Median','Sin mediana','Aucune médiane'],
    'no fictitious price will be used': ['nenhum preço fictício será usado','es wird kein fiktiver Preis verwendet','no se utilizará ningún precio ficticio','aucun prix fictif ne sera utilisé'],
    'balance between margin and compatible market': ['equilíbrio entre margem e mercado compatível','Gleichgewicht zwischen Marge und kompatiblem Markt','equilibrio entre margen y mercado compatible','équilibre entre marge et marché compatible'],
    'no estimated market profit': ['sem lucro estimado de mercado','kein geschätzter Marktgewinn','sin beneficio de mercado estimado','aucun bénéfice de marché estimé'],
    'No relevant alerts for the assumptions provided.': ['Nenhum alerta relevante nas premissas informadas.','Keine relevanten Warnungen für die angegebenen Annahmen.','No hay alertas relevantes para las premisas indicadas.','Aucune alerte pertinente pour les hypothèses fournies.'],
    'Quick sale': ['Venda rápida','Schneller Verkauf','Venta rápida','Vente rapide'],
    'best balance': ['melhor equilíbrio','bestes Gleichgewicht','mejor equilibrio','meilleur équilibre'],
    'More margin': ['Mais margem','Mehr Marge','Más margen','Plus de marge'],
    'higher profit': ['lucro ampliado','höherer Gewinn','beneficio ampliado','bénéfice accru'],
    'high positioning': ['posicionamento alto','hohe Positionierung','posicionamiento alto','positionnement élevé'],
    'RECOMMENDED BY AI': ['RECOMENDADO PELA IA','VON KI EMPFOHLEN','RECOMENDADO POR IA','RECOMMANDÉ PAR L’IA'],
    'live source': ['fonte ao vivo','Live-Quelle','fuente en vivo','source en direct'],
    'fallback rate': ['taxa de contingência','Fallback-Kurs','tasa de contingencia','taux de secours'],
    'No reference': ['Sem referência','Keine Referenz','Sin referencia','Aucune référence'],
    'cost-only simulation': ['simulação baseada só nos custos','Simulation nur auf Kostenbasis','simulación basada solo en costes','simulation basée uniquement sur les coûts'],
    'Average': ['Média','Durchschnitt','Media','Moyenne'],
    'imported': ['importado','importiert','importado','importé'],
    'No source returned compatible listings.': ['Nenhuma fonte retornou anúncios compatíveis.','Keine Quelle lieferte kompatible Angebote.','Ninguna fuente devolvió anuncios compatibles.','Aucune source n’a renvoyé d’annonces compatibles.'],
    'Purchase': ['Compra','Einkauf','Compra','Achat'],
    'Freight': ['Frete','Fracht','Flete','Fret'],
    'Import': ['Importação','Import','Importación','Importation'],
    'Packaging': ['Embalagem','Verpackung','Embalaje','Emballage'],
    'Other': ['Outros','Sonstige','Otros','Autres'],
    'Enter costs to view the composition.': ['Informe custos para visualizar a composição.','Kosten eingeben, um die Zusammensetzung zu sehen.','Introduce costes para ver la composición.','Saisissez les coûts pour voir la composition.'],
    'No compatible listing to display.': ['Nenhum anúncio compatível para exibir.','Kein kompatibles Angebot zum Anzeigen.','No hay anuncios compatibles para mostrar.','Aucune annonce compatible à afficher.'],
    'incompatible': ['incompatível','inkompatibel','incompatible','incompatible'],
    'No saved analysis yet.': ['Nenhuma análise salva ainda.','Noch keine gespeicherte Analyse.','Aún no hay análisis guardados.','Aucune analyse enregistrée pour le moment.'],
    'reliable market': ['mercado confiável','zuverlässiger Markt','mercado fiable','marché fiable'],
    'ambiguous variant': ['variante ambígua','mehrdeutige Variante','variante ambigua','variante ambiguë'],
    'insufficient sample': ['amostra insuficiente','unzureichende Stichprobe','muestra insuficiente','échantillon insuffisant'],
    'no match': ['sem match','kein Match','sin match','aucune correspondance'],
    'no source': ['sem fonte','keine Quelle','sin fuente','aucune source'],
    'The chart appears when there are analyses with reliable market data.': ['O gráfico aparece quando houver análises com mercado confiável.','Das Diagramm erscheint bei Analysen mit zuverlässigen Marktdaten.','El gráfico aparece cuando hay análisis con mercado fiable.','Le graphique apparaît lorsqu’il existe des analyses avec des données de marché fiables.'],
    'No monitored product.': ['Nenhum produto monitorado.','Kein überwachtes Produkt.','Ningún producto monitoreado.','Aucun produit surveillé.'],
    'Reanalyze': ['Reanalisar','Neu analysieren','Reanalizar','Réanalyser'],
    'SAVED': ['SALVA','GESPEICHERT','GUARDADA','ENREGISTRÉE'],
    'NOT CONFIGURED': ['NÃO CONFIGURADA','NICHT KONFIGURIERT','NO CONFIGURADA','NON CONFIGURÉE'],
    'Test connection': ['Testar conexão','Verbindung testen','Probar conexión','Tester la connexion'],
    'Could not load status': ['Não consegui carregar o status','Status konnte nicht geladen werden','No se pudo cargar el estado','Impossible de charger le statut'],
    'Remove': ['Remover','Entfernen','Eliminar','Supprimer'],
    'No device linked.': ['Nenhum dispositivo vinculado.','Kein Gerät verknüpft.','Ningún dispositivo vinculado.','Aucun appareil lié.'],
    'Could not load devices.': ['Não foi possível carregar dispositivos.','Geräte konnten nicht geladen werden.','No se pudieron cargar los dispositivos.','Impossible de charger les appareils.'],
    'MarketAI Community · free · open source · data linked to your account.': ['MarketAI Community · gratuito · open source · dados vinculados à sua conta.','MarketAI Community · kostenlos · Open Source · Daten mit deinem Konto verknüpft.','MarketAI Community · gratis · open source · datos vinculados a tu cuenta.','MarketAI Community · gratuit · open source · données liées à votre compte.'],
    'Excellent opportunity': ['Excelente oportunidade','Ausgezeichnete Chance','Excelente oportunidad','Excellente opportunité'],
    'Good opportunity': ['Boa oportunidade','Gute Chance','Buena oportunidad','Bonne opportunité'],
    'Moderate opportunity': ['Oportunidade moderada','Moderate Chance','Oportunidad moderada','Opportunité modérée'],
    'Tight margin': ['Margem apertada','Knappe Marge','Margen ajustado','Marge serrée'],
    'No reliable market': ['Sem mercado confiável','Kein zuverlässiger Markt','Sin mercado fiable','Aucun marché fiable'],
    'Compatible sample for pricing': ['Amostra compatível para cálculo','Kompatible Stichprobe für Preisberechnung','Muestra compatible para cálculo','Échantillon compatible pour le calcul'],
    'Ambiguous product': ['Produto ambíguo','Mehrdeutiges Produkt','Producto ambiguo','Produit ambigu'],
    'No compatible listing': ['Nenhum anúncio compatível','Kein kompatibles Angebot','Ningún anuncio compatible','Aucune annonce compatible'],
    'No real market data': ['Sem dados reais de mercado','Keine realen Marktdaten','Sin datos reales de mercado','Aucune donnée réelle de marché'],
    'Different variants were found and will not be mixed.': ['Foram encontradas variantes diferentes e elas não serão misturadas.','Unterschiedliche Varianten wurden gefunden und werden nicht gemischt.','Se encontraron variantes diferentes y no se mezclarán.','Différentes variantes ont été trouvées et ne seront pas mélangées.'],
    'No source returned real listings; MarketAI does not fabricate prices.': ['Nenhuma fonte retornou anúncios reais; o MarketAI não fabrica preços.','Keine Quelle lieferte reale Angebote; MarketAI erfindet keine Preise.','Ninguna fuente devolvió anuncios reales; MarketAI no inventa precios.','Aucune source n’a renvoyé d’annonces réelles ; MarketAI n’invente pas de prix.'],
    'Refine the variant or try another source.': ['Refine a variante ou tente outra fonte.','Variante präzisieren oder andere Quelle versuchen.','Refina la variante o prueba otra fuente.','Affinez la variante ou essayez une autre source.'],
    'INSUFFICIENT MARKET DATA': ['DADOS DE MERCADO INSUFICIENTES','UNZUREICHENDE MARKTDATEN','DATOS DE MERCADO INSUFICIENTES','DONNÉES DE MARCHÉ INSUFFISANTES'],
    'I WOULD NOT ENTER NOW': ['NÃO ENTRARIA AGORA','ICH WÜRDE JETZT NICHT EINSTEIGEN','NO ENTRARÍA AHORA','JE N’ENTRERAIS PAS MAINTENANT'],
    'Compatible market found and filtered by variant.': ['Mercado compatível encontrado e filtrado por variante.','Kompatibler Markt gefunden und nach Variante gefiltert.','Mercado compatible encontrado y filtrado por variante.','Marché compatible trouvé et filtré par variante.'],
    'Analysis executed by MarketAI Cloud with credentials kept exclusively on the server.': ['Análise executada pelo MarketAI Cloud com credenciais mantidas exclusivamente no servidor.','Analyse durch MarketAI Cloud mit ausschließlich serverseitig gespeicherten Zugangsdaten.','Análisis ejecutado por MarketAI Cloud con credenciales almacenadas exclusivamente en el servidor.','Analyse exécutée par MarketAI Cloud avec des identifiants conservés exclusivement sur le serveur.'],
    'Stable': ['estável','stabil','estable','stable'],
    'At least 2 real snapshots are required.': ['São necessários pelo menos 2 snapshots reais.','Mindestens 2 reale Snapshots sind erforderlich.','Se requieren al menos 2 snapshots reales.','Au moins 2 snapshots réels sont nécessaires.'],
    'Preview': ['Prévia','Vorschau','Vista previa','Aperçu'],
    'E.g.:': ['Ex.:','Z. B.:','Ej.:','Ex. :'],
    'Brazilian real': ['Real','Brasilianischer Real','Real brasileño','Réal brésilien'],
    'Authenticated ML': ['ML autenticado','Authentifiziertes ML','ML autenticado','ML authentifié'],
    'Incorrect email or password.': ['E-mail ou senha incorretos.','E-Mail oder Passwort falsch.','Correo o contraseña incorrectos.','E-mail ou mot de passe incorrect.'],
    'This email already has an account.': ['Este e-mail já possui uma conta.','Für diese E-Mail existiert bereits ein Konto.','Este correo ya tiene una cuenta.','Cet e-mail possède déjà un compte.'],
    'Enter a valid email and a password with at least 8 characters.': ['Informe um e-mail válido e uma senha com pelo menos 8 caracteres.','Gib eine gültige E-Mail und ein Passwort mit mindestens 8 Zeichen ein.','Introduce un correo válido y una contraseña de al menos 8 caracteres.','Saisissez un e-mail valide et un mot de passe d’au moins 8 caractères.'],
    'You must accept the terms to create the account.': ['É necessário aceitar os termos para criar a conta.','Du musst die Bedingungen akzeptieren, um das Konto zu erstellen.','Debes aceptar los términos para crear la cuenta.','Vous devez accepter les conditions pour créer le compte.'],
    'This account is disabled.': ['Esta conta está desativada.','Dieses Konto ist deaktiviert.','Esta cuenta está desactivada.','Ce compte est désactivé.'],
    'MarketAI Cloud is currently unavailable. Try again in a moment.': ['O MarketAI Cloud está indisponível no momento. Tente novamente em instantes.','MarketAI Cloud ist derzeit nicht verfügbar. Versuche es gleich erneut.','MarketAI Cloud no está disponible en este momento. Inténtalo de nuevo en unos instantes.','MarketAI Cloud est actuellement indisponible. Réessayez dans un instant.'],
    'MarketAI account': ['Conta MarketAI','MarketAI-Konto','Cuenta MarketAI','Compte MarketAI'],
    'Saved': ['Salvo','Gespeichert','Guardado','Enregistré'],
    'Monitored ✓': ['✓ Monitorado','✓ Beobachtet','✓ Monitoreado','✓ Surveillé'],
    'USED FOR PRICING': ['USADO NO CÁLCULO','FÜR PREISBERECHNUNG VERWENDET','USADO EN EL CÁLCULO','UTILISÉ DANS LE CALCUL'],
    'COMPATIBLE': ['COMPATÍVEL','KOMPATIBEL','COMPATIBLE','COMPATIBLE'],
    'DISCARDED': ['DESCARTADO','VERWORFEN','DESCARTADO','ÉCARTÉ'],
    'Variant': ['Variante','Variante','Variante','Variante'],
    'Quality': ['Qualidade','Qualität','Calidad','Qualité'],
    'Score': ['Score','Score','Score','Score'],
    'Verdict': ['Veredito','Urteil','Veredicto','Verdict'],
    'Minimum price for target margin': ['Piso pela margem','Mindestpreis für Zielmarge','Precio mínimo por margen objetivo','Prix minimum pour la marge cible'],
    'Original price': ['Preço original','Originalpreis','Precio original','Prix d’origine'],
    'BRL price': ['Preço BRL','BRL-Preis','Precio BRL','Prix BRL'],
    'Reason': ['Motivo','Grund','Motivo','Motif'],
    'condition is not new': ['condição diferente de novo','Zustand ist nicht neu','condición distinta de nuevo','état différent de neuf'],
    'brand does not match title': ['marca não confere no título','Marke stimmt nicht mit dem Titel überein','la marca no coincide con el título','la marque ne correspond pas au titre'],
    'model does not match': ['modelo não confere','Modell stimmt nicht überein','el modelo no coincide','le modèle ne correspond pas'],
    'highly compatible name': ['nome altamente compatível','Name sehr kompatibel','nombre altamente compatible','nom très compatible'],
    'low name compatibility': ['nome pouco compatível','geringe Namenskompatibilität','baja compatibilidad del nombre','faible compatibilité du nom'],
    'replica': ['réplica','Replik','réplica','réplique'],
    'power': ['potência','Leistung','potencia','puissance'],
    'concentration matches': ['concentração confere','Konzentration stimmt überein','la concentración coincide','la concentration correspond'],
    'MarketAI Community does not create fictitious market prices. If there are fewer than 3 compatible real listings, or variants are mixed, it only shows the minimum price calculated from your costs and blocks the market recommendation. Listing compatibility does not prove physical authenticity. NCM and taxation must be validated with an accountant/customs professional.': ['O MarketAI v1.0.4 Community não cria preços de mercado fictícios. Se não houver pelo menos 3 anúncios reais compatíveis, ou se as variantes estiverem misturadas, ele mostra apenas o preço mínimo calculado pelos seus custos e bloqueia a recomendação de mercado. Compatibilidade de anúncio não comprova autenticidade física do produto. NCM e tributação devem ser validados com contador/despachante.','MarketAI Community erstellt keine fiktiven Marktpreise. Gibt es weniger als 3 kompatible reale Angebote oder werden Varianten gemischt, wird nur der aus deinen Kosten berechnete Mindestpreis angezeigt und die Marktempfehlung gesperrt. Angebotskompatibilität beweist keine physische Echtheit. NCM und Steuern müssen mit Fachleuten geprüft werden.','MarketAI Community no crea precios de mercado ficticios. Si hay menos de 3 anuncios reales compatibles o se mezclan variantes, solo muestra el precio mínimo calculado a partir de tus costes y bloquea la recomendación de mercado. La compatibilidad del anuncio no demuestra la autenticidad física. El NCM y la tributación deben validarse con profesionales.','MarketAI Community ne crée pas de prix de marché fictifs. S’il y a moins de 3 annonces réelles compatibles ou si des variantes sont mélangées, seul le prix minimum calculé à partir de vos coûts est affiché et la recommandation de marché est bloquée. La compatibilité d’une annonce ne prouve pas l’authenticité physique. Le NCM et la fiscalité doivent être validés par des professionnels.']
  };

  const LANG_INDEX = { 'pt-BR': 0, de: 1, es: 2, fr: 3 };
  const PT_TO_EN = new Map();
  Object.entries(C).forEach(([en, arr]) => {
    const pt = arr[0];
    if (pt && !PT_TO_EN.has(pt)) PT_TO_EN.set(pt, en);
  });

  const textSources = new WeakMap();
  const attrSources = new WeakMap();
  let current = localStorage.getItem(STORAGE_KEY);
  if (!SUPPORTED[current]) current = 'en';
  let applying = false;

  const canonical = (value) => {
    const raw = String(value ?? '').trim();
    return C[raw] ? raw : (PT_TO_EN.get(raw) || raw);
  };

  function exact(value, lang=current) {
    const key = canonical(value);
    if (lang === 'en') return key;
    const idx = LANG_INDEX[lang];
    return C[key]?.[idx] || key;
  }

  function dynamic(value, lang=current) {
    const input = String(value ?? '');
    const trimmed = input.trim();
    const direct = exact(trimmed, lang);
    if (direct !== canonical(trimmed) || C[canonical(trimmed)]) return direct;

    const patterns = [
      {
        re: /^(\d+)\s+compatível\(is\)\s+·\s+(\d+)\s+usados no cálculo$/,
        en: m => `${m[1]} compatible · ${m[2]} used for pricing`,
        'pt-BR': m => `${m[1]} compatível(is) · ${m[2]} usados no cálculo`,
        de: m => `${m[1]} kompatibel · ${m[2]} für die Berechnung verwendet`,
        es: m => `${m[1]} compatibles · ${m[2]} usados en el cálculo`,
        fr: m => `${m[1]} compatibles · ${m[2]} utilisés dans le calcul`
      },
      {
        re: /^(\d+)\s+descartado\(s\)$/,
        en: m => `${m[1]} discarded`,
        'pt-BR': m => `${m[1]} descartado(s)`,
        de: m => `${m[1]} verworfen`,
        es: m => `${m[1]} descartados`,
        fr: m => `${m[1]} écartés`
      },
      {
        re: /^Salvo\s+(.+)\s+·\s+(.+)$/,
        en: m => `Saved ${m[1]} · ${dynamic(m[2], 'en')}`,
        'pt-BR': m => `Salvo ${m[1]} · ${dynamic(m[2], 'pt-BR')}`,
        de: m => `Gespeichert ${m[1]} · ${dynamic(m[2], 'de')}`,
        es: m => `Guardado ${m[1]} · ${dynamic(m[2], 'es')}`,
        fr: m => `Enregistré ${m[1]} · ${dynamic(m[2], 'fr')}`
      },
      {
        re: /^Coleta:\s+(.+)\s+·\s+(\d+)\s+fonte\(s\) respondendo\s+·\s+(\d+)\s+loja\(s\)\/vendedor\(es\)$/,
        en: m => `Collected: ${m[1]} · ${m[2]} source(s) responding · ${m[3]} store(s)/seller(s)`,
        'pt-BR': m => `Coleta: ${m[1]} · ${m[2]} fonte(s) respondendo · ${m[3]} loja(s)/vendedor(es)`,
        de: m => `Erfasst: ${m[1]} · ${m[2]} Quelle(n) antworten · ${m[3]} Shop(s)/Verkäufer`,
        es: m => `Recopilado: ${m[1]} · ${m[2]} fuente(s) respondiendo · ${m[3]} tienda(s)/vendedor(es)`,
        fr: m => `Collecté : ${m[1]} · ${m[2]} source(s) répondent · ${m[3]} boutique(s)/vendeur(s)`
      },
      {
        re: /^Busca:\s+(.+)\s+·\s+(.+)$/,
        en: m => `Search: ${m[1]} · ${dynamic(m[2], 'en')}`,
        'pt-BR': m => `Busca: ${m[1]} · ${dynamic(m[2], 'pt-BR')}`,
        de: m => `Suche: ${m[1]} · ${dynamic(m[2], 'de')}`,
        es: m => `Búsqueda: ${m[1]} · ${dynamic(m[2], 'es')}`,
        fr: m => `Recherche : ${m[1]} · ${dynamic(m[2], 'fr')}`
      },
      {
        re: /^Sua conta\s+(.+)\s+foi criada com sucesso\. Todos os recursos Community estão liberados gratuitamente\.$/,
        en: m => `Your account ${m[1]} was created successfully. All Community features are unlocked for free.`,
        'pt-BR': m => `Sua conta ${m[1]} foi criada com sucesso. Todos os recursos Community estão liberados gratuitamente.`,
        de: m => `Dein Konto ${m[1]} wurde erfolgreich erstellt. Alle Community-Funktionen sind kostenlos freigeschaltet.`,
        es: m => `Tu cuenta ${m[1]} se creó correctamente. Todas las funciones Community están desbloqueadas gratis.`,
        fr: m => `Votre compte ${m[1]} a été créé avec succès. Toutes les fonctionnalités Community sont débloquées gratuitement.`
      },
      {
        re: /^Pasta de dados:\s*(.+)$/,
        en: m => `Data folder: ${m[1]}`,
        'pt-BR': m => `Pasta de dados: ${m[1]}`,
        de: m => `Datenordner: ${m[1]}`,
        es: m => `Carpeta de datos: ${m[1]}`,
        fr: m => `Dossier de données : ${m[1]}`
      },
      {
        re: /^Não consegui carregar o status:\s*(.+)$/,
        en: m => `Could not load status: ${m[1]}`,
        'pt-BR': m => `Não consegui carregar o status: ${m[1]}`,
        de: m => `Status konnte nicht geladen werden: ${m[1]}`,
        es: m => `No se pudo cargar el estado: ${m[1]}`,
        fr: m => `Impossible de charger le statut : ${m[1]}`
      }
    ];

    for (const p of patterns) {
      const m = trimmed.match(p.re);
      if (m) return (p[lang] || p.en)(m);
    }

    // Translate known Portuguese fragments inside labels such as country/currency
    // options ("🇧🇷 Brasil", "BRL — Real") and example placeholders.
    let partial = trimmed;
    const aliases = [...PT_TO_EN.entries()]
      .filter(([pt]) => pt.length >= 3)
      .sort((a,b) => b[0].length - a[0].length);
    for (const [pt, enKey] of aliases) {
      if (!partial.includes(pt)) continue;
      const replacement = lang === 'en'
        ? enKey
        : (C[enKey]?.[LANG_INDEX[lang]] || enKey);
      partial = partial.split(pt).join(replacement);
    }
    return partial;
  }

  function preserveWhitespace(original, translated) {
    const lead = original.match(/^\s*/)?.[0] || '';
    const tail = original.match(/\s*$/)?.[0] || '';
    return lead + translated + tail;
  }

  function translateTextNode(node, forceSource=false) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    const raw = node.nodeValue || '';
    if (!raw.trim()) return;
    if (forceSource || !textSources.has(node)) textSources.set(node, raw.trim());
    const src = textSources.get(node);
    const out = dynamic(src, current);
    const next = preserveWhitespace(raw, out);
    if (next !== raw) node.nodeValue = next;
  }

  function translateAttrs(el, forceSource=false) {
    if (!(el instanceof Element)) return;
    const attrs = ['placeholder','title','alt','aria-label'];
    let cache = attrSources.get(el);
    if (!cache) { cache = {}; attrSources.set(el, cache); }
    for (const attr of attrs) {
      if (!el.hasAttribute(attr)) continue;
      const now = el.getAttribute(attr) || '';
      if (forceSource || cache[attr] == null) cache[attr] = now;
      const out = dynamic(cache[attr], current);
      if (out !== now) el.setAttribute(attr, out);
    }
  }

  function translateTree(root=document.body) {
    if (!root) return;
    applying = true;
    try {
      if (root.nodeType === Node.TEXT_NODE) translateTextNode(root);
      if (root instanceof Element) translateAttrs(root);
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = walker.nextNode())) translateTextNode(n);
      if (root.querySelectorAll) root.querySelectorAll('*').forEach(el => translateAttrs(el));
      document.documentElement.lang = current === 'pt-BR' ? 'pt-BR' : current;
      document.title = exact('MarketAI — Market Intelligence', current);
      document.querySelectorAll('[data-language-select]').forEach(sel => { sel.value = current; });
    } finally { applying = false; }
  }

  function setLanguage(lang, {persist=true}={}) {
    if (!SUPPORTED[lang]) lang = 'en';
    current = lang;
    if (persist) localStorage.setItem(STORAGE_KEY, lang);
    translateTree(document.body);
    document.dispatchEvent(new CustomEvent('marketai:languagechange', {detail:{language:lang, locale:SUPPORTED[lang].locale}}));
  }

  const nativeAlert = window.alert.bind(window);
  window.alert = (message) => nativeAlert(dynamic(String(message), current));
  const nativeConfirm = window.confirm.bind(window);
  window.confirm = (message) => nativeConfirm(dynamic(String(message), current));

  function bindSelectors() {
    document.querySelectorAll('[data-language-select]').forEach(select => {
      select.value = current;
      if (select.dataset.boundLanguage === '1') return;
      select.dataset.boundLanguage = '1';
      select.addEventListener('change', () => setLanguage(select.value));
    });
  }

  const observer = new MutationObserver(mutations => {
    if (applying) return;
    applying = true;
    try {
      for (const m of mutations) {
        if (m.type === 'characterData') {
          const raw = m.target.nodeValue || '';
          const existing = textSources.get(m.target);
          if (existing) {
            const expected = preserveWhitespace(raw, dynamic(existing, current));
            if (raw === expected) continue;
          }
          if (raw.trim()) textSources.set(m.target, raw.trim());
          translateTextNode(m.target);
        } else if (m.type === 'childList') {
          m.addedNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) translateTextNode(node, true);
            else if (node instanceof Element) translateTree(node);
          });
        } else if (m.type === 'attributes' && m.target instanceof Element) {
          const cache = attrSources.get(m.target) || {};
          const attr = m.attributeName;
          const raw = attr ? (m.target.getAttribute(attr) || '') : '';
          if (attr && cache[attr] != null && raw === dynamic(cache[attr], current)) continue;
          translateAttrs(m.target, true);
        }
      }
      bindSelectors();
    } finally { applying = false; }
  });

  window.MarketI18n = {
    languages: SUPPORTED,
    language: () => current,
    locale: () => SUPPORTED[current]?.locale || 'en-US',
    t: (value) => dynamic(value, current),
    setLanguage,
    refresh: () => translateTree(document.body)
  };

  function boot() {
    bindSelectors();
    translateTree(document.body);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['placeholder','title','alt','aria-label']
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, {once:true});
  else boot();
})();
