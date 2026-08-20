#!/usr/bin/env python3
"""
HARVESTER MASSIVO DE CÂMERAS REAIS AO VIVO (YOUTUBE LIVE) — 1000+ CÂMERAS
Busca transmissões públicas 100% reais, sem simulação ou dados mockados.
Salva em database/live_cameras.json
"""
import sys
import json
import time
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "database" / "live_cameras.json"

QUERIES = [
    # ── BRASIL (ESTADOS, PRAIAS, PONTOS TURÍSTICOS, TRÂNSITO, AEROPORTOS) ──
    ("camera ao vivo sao paulo transito sp", "BR", "São Paulo, SP"),
    ("camera ao vivo avenida paulista", "BR", "São Paulo - Av. Paulista, SP"),
    ("camera ao vivo marginal pinheiros tiete", "BR", "São Paulo - Marginais, SP"),
    ("camera ao vivo aeroporto guarulhos gru", "BR", "Aeroporto GRU, SP"),
    ("camera ao vivo aeroporto congonhas cgh", "BR", "Aeroporto CGH, SP"),
    ("camera ao vivo aeroporto viracopos vcp", "BR", "Aeroporto VCP, SP"),
    ("camera ao vivo santos praia orla", "BR", "Santos, SP"),
    ("camera ao vivo guaruja pitangueiras enseada", "BR", "Guarujá, SP"),
    ("camera ao vivo bertioga riviera", "BR", "Bertioga, SP"),
    ("camera ao vivo sao sebastiao maresias", "BR", "São Sebastião, SP"),
    ("camera ao vivo ilhabela praia", "BR", "Ilhabela, SP"),
    ("camera ao vivo ubatuba praia grande itamambuca", "BR", "Ubatuba, SP"),
    ("camera ao vivo campos do jordao serra da mantiqueira", "BR", "Campos do Jordão, SP"),
    ("camera ao vivo porto de santos canal", "BR", "Porto de Santos, SP"),
    ("camera ao vivo rodovia anchieta imigrantes", "BR", "Rodovia Anchieta-Imigrantes, SP"),
    ("camera ao vivo rodovia presidente dutra", "BR", "Rodovia Pres. Dutra, SP/RJ"),
    ("camera ao vivo rodovia anhanguera bandeirantes", "BR", "Rodovia Anhanguera/Bandeirantes, SP"),
    ("camera ao vivo rodovia castello branco", "BR", "Rodovia Castello Branco, SP"),
    ("camera ao vivo rodovia ayrton senna carvalho pinto", "BR", "Rodovia Ayrton Senna, SP"),
    ("camera ao vivo rodovia regis bittencourt", "BR", "Rodovia Régis Bittencourt, SP/PR"),
    ("camera ao vivo campinas sp", "BR", "Campinas, SP"),
    ("camera ao vivo ribeirao preto sp", "BR", "Ribeirão Preto, SP"),
    ("camera ao vivo sao jose dos campos sp", "BR", "São José dos Campos, SP"),
    ("camera ao vivo sorocaba sp", "BR", "Sorocaba, SP"),
    ("camera ao vivo bauru sp", "BR", "Bauru, SP"),
    ("camera ao vivo piracicaba sp", "BR", "Piracicaba, SP"),
    ("camera ao vivo presidente prudente sp", "BR", "Presidente Prudente, SP"),
    ("camera ao vivo sao carlos sp", "BR", "São Carlos, SP"),
    ("camera ao vivo franca sp", "BR", "Franca, SP"),
    ("camera ao vivo rio de janeiro copacabana", "BR", "Rio de Janeiro - Copacabana, RJ"),
    ("camera ao vivo rio de janeiro ipanema leblon", "BR", "Rio de Janeiro - Ipanema, RJ"),
    ("camera ao vivo cristo redentor corcovado", "BR", "Rio de Janeiro - Cristo Redentor, RJ"),
    ("camera ao vivo pao de acucar urca", "BR", "Rio de Janeiro - Pão de Açúcar, RJ"),
    ("camera ao vivo barra da tijuca recreio rj", "BR", "Rio de Janeiro - Barra da Tijuca, RJ"),
    ("camera ao vivo aeroporto galeao santos dumont", "BR", "Aeroporto Galeão / SDU, RJ"),
    ("camera ao vivo ponte rio niteroi", "BR", "Ponte Rio-Niterói, RJ"),
    ("camera ao vivo cabo frio praia do forte", "BR", "Cabo Frio, RJ"),
    ("camera ao vivo arraial do cabo praia grande", "BR", "Arraial do Cabo, RJ"),
    ("camera ao vivo buzios geriba rua das pedras", "BR", "Búzios, RJ"),
    ("camera ao vivo angra dos reis ilha grande", "BR", "Angra dos Reis, RJ"),
    ("camera ao vivo paraty rj", "BR", "Paraty, RJ"),
    ("camera ao vivo petropolis rj serra", "BR", "Petrópolis, RJ"),
    ("camera ao vivo teresopolis rj dedo de deus", "BR", "Teresópolis, RJ"),
    ("camera ao vivo niteroi icaraf praia", "BR", "Niterói, RJ"),
    ("camera ao vivo balneario camboriu sc praia central", "BR", "Balneário Camboriú, SC"),
    ("camera ao vivo florianopolis praia mole joaquina", "BR", "Florianópolis, SC"),
    ("camera ao vivo florianopolis jurere canasvieiras ingleses", "BR", "Florianópolis - Norte da Ilha, SC"),
    ("camera ao vivo florianopolis campeche morro das pedras", "BR", "Florianópolis - Sul da Ilha, SC"),
    ("camera ao vivo ponte hercilio luz florianopolis", "BR", "Florianópolis - Ponte Hercílio Luz, SC"),
    ("camera ao vivo bombinhas sc quatro ilhas mariscal", "BR", "Bombinhas, SC"),
    ("camera ao vivo itapema sc meia praia", "BR", "Itapema, SC"),
    ("camera ao vivo itajai sc praia brava", "BR", "Itajaí - Praia Brava, SC"),
    ("camera ao vivo joinville sc", "BR", "Joinville, SC"),
    ("camera ao vivo blumenau sc", "BR", "Blumenau, SC"),
    ("camera ao vivo tubarao criciuma sc", "BR", "Criciúma / Tubarão, SC"),
    ("camera ao vivo garopaba praia do rosa sc", "BR", "Garopaba, SC"),
    ("camera ao vivo serra do rio do rastro sc", "BR", "Serra do Rio do Rastro, SC"),
    ("camera ao vivo sao joaquim urubici sc serra", "BR", "São Joaquim / Urubici, SC"),
    ("camera ao vivo aeroporto navegantes nvt", "BR", "Aeroporto Navegantes, SC"),
    ("camera ao vivo aeroporto florianopolis fln", "BR", "Aeroporto Florianópolis, SC"),
    ("camera ao vivo porto alegre guaiba orla", "BR", "Porto Alegre, RS"),
    ("camera ao vivo aeroporto porto alegre salgado filho", "BR", "Aeroporto Porto Alegre, RS"),
    ("camera ao vivo gramado canela rs", "BR", "Gramado / Canela, RS"),
    ("camera ao vivo caxias do sul serra gaucha rs", "BR", "Caxias do Sul, RS"),
    ("camera ao vivo torres rs praia", "BR", "Torres, RS"),
    ("camera ao vivo capao da canoa xangrila rs", "BR", "Capão da Canoa, RS"),
    ("camera ao vivo tramandai imbe rs", "BR", "Tramandaí, RS"),
    ("camera ao vivo pelotas rio grande rs", "BR", "Pelotas / Rio Grande, RS"),
    ("camera ao vivo passo fundo rs", "BR", "Passo Fundo, RS"),
    ("camera ao vivo santa maria rs", "BR", "Santa Maria, RS"),
    ("camera ao vivo curitiba pr parque barigui", "BR", "Curitiba, PR"),
    ("camera ao vivo curitiba pr jardim botanico", "BR", "Curitiba, PR"),
    ("camera ao vivo aeroporto curitiba afonso pena", "BR", "Aeroporto CWB, PR"),
    ("camera ao vivo foz do iguacu cataratas ponte amizade", "BR", "Foz do Iguaçu, PR"),
    ("camera ao vivo londrina pr", "BR", "Londrina, PR"),
    ("camera ao vivo maringa pr", "BR", "Maringá, PR"),
    ("camera ao vivo ponta grossa pr", "BR", "Ponta Grossa, PR"),
    ("camera ao vivo cascavel pr", "BR", "Cascavel, PR"),
    ("camera ao vivo guaratuba matinhos caioba pr", "BR", "Litoral do Paraná, PR"),
    ("camera ao vivo porto de paranagua pr", "BR", "Porto de Paranaguá, PR"),
    ("camera ao vivo salvador farol da barra rio vermelho", "BR", "Salvador, BA"),
    ("camera ao vivo salvador pelourinho elevador lacerda", "BR", "Salvador - Pelourinho, BA"),
    ("camera ao vivo porto seguro trancoso arraial ajuda", "BR", "Porto Seguro / Trancoso, BA"),
    ("camera ao vivo ilheus itacare bahia", "BR", "Ilhéus / Itacaré, BA"),
    ("camera ao vivo morro de sao paulo boipeba ba", "BR", "Morro de São Paulo, BA"),
    ("camera ao vivo feira de santana bahia", "BR", "Feira de Santana, BA"),
    ("camera ao vivo vitoria da conquista bahia", "BR", "Vitória da Conquista, BA"),
    ("camera ao vivo praia do forte bahia", "BR", "Praia do Forte, BA"),
    ("camera ao vivo recife marco zero boa viagem", "BR", "Recife, PE"),
    ("camera ao vivo olinda pe alto da se", "BR", "Olinda, PE"),
    ("camera ao vivo porto de galinhas muro alto pe", "BR", "Porto de Galinhas, PE"),
    ("camera ao vivo fernando de noronha live", "BR", "Fernando de Noronha, PE"),
    ("camera ao vivo caruaru petrolina pe", "BR", "Caruaru / Petrolina, PE"),
    ("camera ao vivo fortaleza beira mar praia de iracema", "BR", "Fortaleza, CE"),
    ("camera ao vivo fortaleza praia do futuro", "BR", "Fortaleza, CE"),
    ("camera ao vivo jericoacoara ce duna do por do sol", "BR", "Jericoacoara, CE"),
    ("camera ao vivo canoa quebrada ce", "BR", "Canoa Quebrada, CE"),
    ("camera ao vivo natal rn ponta negra morro do careca", "BR", "Natal, RN"),
    ("camera ao vivo praia da pipa tibau do sul rn", "BR", "Praia da Pipa, RN"),
    ("camera ao vivo joao pessoa tambau cabo branco pb", "BR", "João Pessoa, PB"),
    ("camera ao vivo campina grande pb", "BR", "Campina Grande, PB"),
    ("camera ao vivo maceio ponta verde pajuçara al", "BR", "Maceió, AL"),
    ("camera ao vivo maragogi praia de antunes al", "BR", "Maragogi, AL"),
    ("camera ao vivo sao miguel dos milagres al", "BR", "São Miguel dos Milagres, AL"),
    ("camera ao vivo aracaju orla de atalaia se", "BR", "Aracaju, SE"),
    ("camera ao vivo vitoria es praia de camburi", "BR", "Vitória, ES"),
    ("camera ao vivo vila velha es praia da costa", "BR", "Vila Velha, ES"),
    ("camera ao vivo guarapari es praia do morro", "BR", "Guarapari, ES"),
    ("camera ao vivo belo horizonte bh pampulha praca do papa", "BR", "Belo Horizonte, MG"),
    ("camera ao vivo aeroporto confins cnf", "BR", "Aeroporto Confins (CNF), MG"),
    ("camera ao vivo ouro preto tiradentes mg", "BR", "Ouro Preto / Tiradentes, MG"),
    ("camera ao vivo uberlandia uberaba triangulo mineiro", "BR", "Uberlândia / Uberaba, MG"),
    ("camera ao vivo juiz de fora mg", "BR", "Juiz de Fora, MG"),
    ("camera ao vivo montes claros mg", "BR", "Montes Claros, MG"),
    ("camera ao vivo pocos de caldas mg", "BR", "Poços de Caldas, MG"),
    ("camera ao vivo goiania praca civica parque vaca brava", "BR", "Goiânia, GO"),
    ("camera ao vivo caldas novas go", "BR", "Caldas Novas, GO"),
    ("camera ao vivo pirenopolis goias go", "BR", "Pirenópolis, GO"),
    ("camera ao vivo brasilia esplanada congresso nacional", "BR", "Brasília, DF"),
    ("camera ao vivo aeroporto brasilia bsb", "BR", "Aeroporto BSB, DF"),
    ("camera ao vivo manaus teatro amazonas encontro das aguas", "BR", "Manaus, AM"),
    ("camera ao vivo belem pa estacao das docas mercado ver o peso", "BR", "Belém, PA"),
    ("camera ao vivo cuiaba pantanal chapada dos guimaraes", "BR", "Cuiabá / Pantanal, MT"),
    ("camera ao vivo campo grande ms bonito", "BR", "Campo Grande / Bonito, MS"),
    ("camera ao vivo sao luis ma lencois maranhenses", "BR", "São Luís / Lençóis, MA"),
    ("camera ao vivo teresina pi delta do parnaiba", "BR", "Teresina / Parnaíba, PI"),
    ("camera ao vivo palmas to jalapao", "BR", "Palmas / Jalapão, TO"),
    ("camera ao vivo porto velho rondonia", "BR", "Porto Velho, RO"),
    ("camera ao vivo rio branco acre", "BR", "Rio Branco, AC"),
    ("camera ao vivo boa vista roraima", "BR", "Boa Vista, RR"),
    ("camera ao vivo macapa amapa marco zero", "BR", "Macapá, AP"),

    # ── ESTADOS UNIDOS (TOP WEBCAMS, PRAIAS, METRÓPOLES, NATUREZA) ──
    ("times square new york live webcam 4k", "US", "New York - Times Square, NY"),
    ("broadway 42nd street new york live stream", "US", "New York - Broadway, NY"),
    ("brooklyn bridge lower manhattan live cam", "US", "New York - Brooklyn Bridge, NY"),
    ("central park new york live camera", "US", "New York - Central Park, NY"),
    ("world trade center manhattan skyline live cam", "US", "New York - Manhattan Skyline, NY"),
    ("statue of liberty new york harbor live cam", "US", "New York - Estátua da Liberdade, NY"),
    ("las vegas strip bellagio fountains live camera", "US", "Las Vegas - Bellagio, NV"),
    ("las vegas fremont street live webcam", "US", "Las Vegas - Fremont St, NV"),
    ("las vegas stratosphere live camera", "US", "Las Vegas - Stratosphere, NV"),
    ("miami south beach ocean drive live cam", "US", "Miami Beach - Ocean Drive, FL"),
    ("miami skyline biscayne bay live camera", "US", "Miami - Biscayne Bay, FL"),
    ("key west duval street sloppy joes live cam", "US", "Key West - Duval St, FL"),
    ("key west sunset pier live camera", "US", "Key West - Sunset Pier, FL"),
    ("clearwater beach florida live webcam 4k", "US", "Clearwater Beach, FL"),
    ("daytona beach florida live camera", "US", "Daytona Beach, FL"),
    ("panama city beach florida live cam", "US", "Panama City Beach, FL"),
    ("fort lauderdale beach live camera", "US", "Fort Lauderdale, FL"),
    ("st petersburg florida pier live camera", "US", "St. Petersburg, FL"),
    ("naples pier florida live camera", "US", "Naples, FL"),
    ("pensacola beach florida live cam", "US", "Pensacola Beach, FL"),
    ("destin florida harbor live cam", "US", "Destin, FL"),
    ("los angeles venice beach boardwalk live cam 4k", "US", "Los Angeles - Venice Beach, CA"),
    ("santa monica pier carousel live camera", "US", "Santa Monica Pier, CA"),
    ("hollywood boulevard chinese theatre live cam", "US", "Hollywood Blvd, CA"),
    ("malibu beach california live surf cam", "US", "Malibu Beach, CA"),
    ("huntington beach surf city usa live cam", "US", "Huntington Beach, CA"),
    ("laguna beach california live camera", "US", "Laguna Beach, CA"),
    ("newport beach balboa peninsula live cam", "US", "Newport Beach, CA"),
    ("san diego pacific beach live camera", "US", "San Diego - Pacific Beach, CA"),
    ("san diego coronado beach live cam", "US", "San Diego - Coronado, CA"),
    ("san francisco golden gate bridge live 4k", "US", "San Francisco - Golden Gate, CA"),
    ("san francisco pier 39 alcatraz live cam", "US", "San Francisco - Pier 39, CA"),
    ("san francisco cable car powell street live cam", "US", "San Francisco, CA"),
    ("lake tahoe live webcam 4k california nevada", "US", "Lake Tahoe, CA/NV"),
    ("yosemite falls el capitan live camera", "US", "Yosemite National Park, CA"),
    ("chicago riverwalk michigan avenue live cam", "US", "Chicago - Riverwalk, IL"),
    ("chicago navy pier lake michigan live cam", "US", "Chicago - Navy Pier, IL"),
    ("chicago wrigley field ballpark live camera", "US", "Chicago, IL"),
    ("seattle space needle elliott bay live cam 4k", "US", "Seattle - Space Needle, WA"),
    ("seattle pike place market live camera", "US", "Seattle - Pike Place, WA"),
    ("waikiki beach diamond head live camera 4k", "US", "Honolulu - Waikiki, HI"),
    ("north shore oahu banzai pipeline live surf cam", "US", "Oahu - North Shore, HI"),
    ("maui kaanapali beach live webcam", "US", "Maui, HI"),
    ("kauai poipu beach live camera", "US", "Kauai, HI"),
    ("jackson hole town square live cam elk antlers", "US", "Jackson Hole, WY"),
    ("bourbon street new orleans cats meow live cam", "US", "New Orleans - Bourbon St, LA"),
    ("french quarter new orleans live cam", "US", "New Orleans - French Quarter, LA"),
    ("niagara falls horseshoe falls live camera 4k", "US", "Niagara Falls, NY"),
    ("grand canyon south rim live camera 4k", "US", "Grand Canyon, AZ"),
    ("sedona red rocks live camera arizona", "US", "Sedona, AZ"),
    ("monument valley navajo park live camera", "US", "Monument Valley, AZ/UT"),
    ("yellowstone old faithful geyser live cam 4k", "US", "Yellowstone, WY"),
    ("katmai national park brooks falls bears live", "US", "Katmai National Park, AK"),
    ("alaska anchorage downtown live webcam", "US", "Anchorage, AK"),
    ("washington dc capitol mall monument live cam", "US", "Washington, DC"),
    ("philadelphia liberty bell center city live cam", "US", "Philadelphia, PA"),
    ("boston harbor fan pier skyline live cam", "US", "Boston Harbor, MA"),
    ("denver colorado skyline mountain view live cam", "US", "Denver, CO"),
    ("vail aspen breckenridge colorado ski live cam", "US", "Colorado Ski Resorts, CO"),
    ("austin texas downtown congress ave live cam", "US", "Austin, TX"),
    ("san antonio river walk live webcam", "US", "San Antonio - River Walk, TX"),
    ("galveston beach texas live camera", "US", "Galveston, TX"),
    ("dallas skyline reunion tower live camera", "US", "Dallas, TX"),
    ("houston skyline buffalo bayou live cam", "US", "Houston, TX"),
    ("atlanta skyline centennial park live cam", "US", "Atlanta, GA"),
    ("savannah georgia river street live cam", "US", "Savannah, GA"),
    ("nashville broadway honky tonk highway live cam", "US", "Nashville - Broadway, TN"),
    ("charleston battery harbor live camera south carolina", "US", "Charleston, SC"),
    ("myrtle beach oceanfront live camera", "US", "Myrtle Beach, SC"),
    ("outer banks north carolina live beach cam", "US", "Outer Banks, NC"),
    ("ocean city maryland boardwalk live cam", "US", "Ocean City, MD"),
    ("atlantic city boardwalk new jersey live cam", "US", "Atlantic City, NJ"),
    ("cape cod massachusetts live beach camera", "US", "Cape Cod, MA"),
    ("portland head light maine lighthouse live cam", "US", "Portland Head Light, ME"),

    # ── CANADÁ ──
    ("toronto cn tower harbourfront live camera", "CA", "Toronto, ON"),
    ("vancouver harbour burrard inlet live cam", "CA", "Vancouver, BC"),
    ("banff lake louise alberta rockies live cam", "CA", "Banff - Lake Louise, AB"),
    ("whistler blackcomb ski live camera", "CA", "Whistler, BC"),
    ("montreal old port st lawrence river live cam", "CA", "Montreal, QC"),
    ("quebec city chateau frontenac live camera", "CA", "Quebec City, QC"),
    ("calgary tower skyline live cam", "CA", "Calgary, AB"),
    ("victoria inner harbour british columbia live cam", "CA", "Victoria, BC"),

    # ── EUROPA (UK, FRANÇA, ITÁLIA, ESPANHA, PORTUGAL, ALEMANHA, ETC.) ──
    ("london abbey road crossing live camera", "EU", "London - Abbey Road, UK"),
    ("london tower bridge thames 4k live stream", "EU", "London - Tower Bridge, UK"),
    ("london piccadilly circus live webcam", "EU", "London - Piccadilly Circus, UK"),
    ("london westminster big ben live cam", "EU", "London - Big Ben, UK"),
    ("london eye south bank live camera", "EU", "London - London Eye, UK"),
    ("paris eiffel tower trocadero live camera 4k", "EU", "Paris - Torre Eiffel, França"),
    ("paris seine river notre dame live camera", "EU", "Paris - Rio Sena, França"),
    ("paris montmartre sacre coeur live cam", "EU", "Paris - Montmartre, França"),
    ("cannes promenade croisette live camera", "EU", "Cannes, França"),
    ("nice promenade des anglais live webcam", "EU", "Nice, França"),
    ("chamonix mont blanc alps live camera", "EU", "Chamonix - Mont Blanc, França"),
    ("rome colosseum via dei fori imperiali live cam", "EU", "Roma - Coliseu, Itália"),
    ("rome trevi fountain skylinewebcams live", "EU", "Roma - Fontana di Trevi, Itália"),
    ("rome spanish steps piazza di spagna live cam", "EU", "Roma - Piazza di Spagna, Itália"),
    ("rome vatican st peter square basilica live", "EU", "Vaticano - Praça São Pedro"),
    ("venice rialto bridge grand canal live 4k", "EU", "Veneza - Ponte de Rialto, Itália"),
    ("venice piazza san marco st mark live cam", "EU", "Veneza - Praça San Marco, Itália"),
    ("florence ponte vecchio arno river live cam", "EU", "Florença - Ponte Vecchio, Itália"),
    ("florence duomo santa maria del fiore live cam", "EU", "Florença - Duomo, Itália"),
    ("milan duomo square live camera skylinewebcams", "EU", "Milão - Duomo, Itália"),
    ("amalfi coast positano live camera 4k", "EU", "Costa Amalfitana - Positano, Itália"),
    ("capri faraglioni live camera italy", "EU", "Capri, Itália"),
    ("lake como bellagio live webcam italy", "EU", "Lago de Como, Itália"),
    ("lake garda malcesine live camera italy", "EU", "Lago de Garda, Itália"),
    ("dolomites val gardena ski live camera 4k", "EU", "Dolomitas, Itália"),
    ("madrid puerta del sol plaza mayor live cam", "EU", "Madrid - Puerta del Sol, Espanha"),
    ("madrid gran via live camera 4k", "EU", "Madrid - Gran Vía, Espanha"),
    ("barcelona sagrada familia live cam 4k", "EU", "Barcelona - Sagrada Família, Espanha"),
    ("barcelona barceloneta beach live cam", "EU", "Barcelona - Barceloneta, Espanha"),
    ("barcelona park guell skyline live camera", "EU", "Barcelona, Espanha"),
    ("mallorca palma beach live camera spain", "EU", "Maiorca, Espanha"),
    ("ibiza san antonio sunset live cam", "EU", "Ibiza, Espanha"),
    ("tenerife playa de las americas live camera", "EU", "Tenerife, Canárias, Espanha"),
    ("gran canaria las canteras beach live cam", "EU", "Gran Canária, Espanha"),
    ("sevilla plaza de espana giralda live cam", "EU", "Sevilha, Espanha"),
    ("valencia city of arts and sciences live cam", "EU", "Valência, Espanha"),
    ("lisbon praca do comercio tejo river live cam", "EU", "Lisboa - Praça do Comércio, Portugal"),
    ("lisbon miradouro santa luzia alfama live cam", "EU", "Lisboa - Alfama, Portugal"),
    ("porto ribeira douro dom luis bridge live cam", "EU", "Porto - Rio Douro, Portugal"),
    ("nazare praia do norte big waves live surf cam", "EU", "Nazaré - Ondas Gigantes, Portugal"),
    ("algarve albufeira praia dos pescadores live cam", "EU", "Algarve - Albufeira, Portugal"),
    ("algarve lagos ponta da piedade live cam", "EU", "Algarve - Lagos, Portugal"),
    ("madeira funchal harbour live camera", "EU", "Madeira - Funchal, Portugal"),
    ("amsterdam dam square canals live camera", "EU", "Amsterdã - Dam Square, Holanda"),
    ("amsterdam central station live camera", "EU", "Amsterdã, Holanda"),
    ("rotterdam erasmus bridge harbour live cam", "EU", "Roterdã, Holanda"),
    ("brussels grand place live webcam belgium", "EU", "Bruxelas - Grand Place, Bélgica"),
    ("bruges markt belfry live camera belgium", "EU", "Bruges, Bélgica"),
    ("berlin brandenburg gate live camera 4k", "EU", "Berlim - Portão de Brandemburgo, Alemanha"),
    ("berlin alexanderplatz tv tower live camera", "EU", "Berlim - Alexanderplatz, Alemanha"),
    ("munich marienplatz rathaus live camera", "EU", "Munique - Marienplatz, Alemanha"),
    ("cologne cathedral rhein river live camera", "EU", "Colônia - Catedral, Alemanha"),
    ("hamburg port elbe river live camera", "EU", "Hamburgo - Porto, Alemanha"),
    ("neuschwanstein castle live camera bavaria", "EU", "Castelo de Neuschwanstein, Alemanha"),
    ("swiss alps zermatt matterhorn live cam 4k", "EU", "Alpes Suíços - Matterhorn, Suíça"),
    ("jungfraujoch top of europe live camera", "EU", "Jungfraujoch, Suíça"),
    ("lake geneva jet deau live camera", "EU", "Genebra, Suíça"),
    ("zurich lake limmat river live camera", "EU", "Zurique, Suíça"),
    ("lucerne chapel bridge lake live camera", "EU", "Lucerna, Suíça"),
    ("vienna st stephen cathedral gr ステファン寺院 live cam", "EU", "Viena, Áustria"),
    ("salzburg fortress mozartplatz live cam", "EU", "Salzburgo, Áustria"),
    ("innsbruck alps goldenes dachl live cam", "EU", "Innsbruck, Áustria"),
    ("prague old town square charles bridge 4k live cam", "EU", "Praga, Rep. Tcheca"),
    ("budapest danube chain bridge parliament live cam", "EU", "Budapeste, Hungria"),
    ("warsaw old town castle square live camera", "EU", "Varsóvia, Polônia"),
    ("krakow main market square cloth hall live cam", "EU", "Cracóvia, Polônia"),
    ("dublin temple bar oconnell street live cam", "EU", "Dublin - Temple Bar, Irlanda"),
    ("edinburgh castle princes street live camera", "EU", "Edimburgo, Escócia"),
    ("santorini oia caldera fira live cam 4k", "EU", "Santorini, Grécia"),
    ("mykonos windmills little venice live cam", "EU", "Mykonos, Grécia"),
    ("athens acropolis parthenon live camera 4k", "EU", "Atenas - Acrópole, Grécia"),
    ("dubrovnik old town stradun live camera croatia", "EU", "Dubrovnik, Croácia"),
    ("split riva diocletian palace live camera", "EU", "Split, Croácia"),
    ("reykjavik volcano fagradalsfjall live cam iceland", "EU", "Islândia - Vulcão / Aurora"),
    ("norway geirangerfjord tromso aurora live cam", "EU", "Noruega - Fiordes & Aurora"),
    ("lofoten islands norway live camera 4k", "EU", "Ilhas Lofoten, Noruega"),
    ("stockholm old town gamla stan live camera", "EU", "Estocolmo, Suécia"),
    ("copenhagen nyhavn live webcam denmark", "EU", "Copenhague - Nyhavn, Dinamarca"),
    ("helsinki senate square market square live cam", "EU", "Helsinque, Finlândia"),
    ("istanbul bosphorus galata bridge live 4k", "EU", "Istambul - Bósforo, Turquia"),

    # ── ÁSIA & OCEANIA ──
    ("tokyo shibuya crossing live camera 4k 24/7", "AS", "Tóquio - Shibuya, Japão"),
    ("tokyo shinjuku kabukicho live cam 4k", "AS", "Tóquio - Shinjuku, Japão"),
    ("tokyo tower roppongi hills live camera", "AS", "Tóquio - Tokyo Tower, Japão"),
    ("tokyo akihabara electric town live camera", "AS", "Tóquio - Akihabara, Japão"),
    ("mount fuji lake kawaguchiko live camera 4k", "AS", "Monte Fuji, Japão"),
    ("kyoto doto live camera gion fushimi", "AS", "Kyoto, Japão"),
    ("osaka dotonbori glico man live camera", "AS", "Osaka - Dotonbori, Japão"),
    ("yokohama minato mirai harbour live camera", "AS", "Yokohama, Japão"),
    ("seoul gangnam myeongdong live camera 4k", "AS", "Seul - Myeongdong, Coreia"),
    ("seoul han river namsan tower live stream", "AS", "Seul - Rio Han, Coreia"),
    ("busan haeundae beach live camera korea", "AS", "Busan - Haeundae Beach, Coreia"),
    ("hong kong victoria harbour tsim sha tsui live 4k", "AS", "Hong Kong - Victoria Harbour"),
    ("taipei 101 skyline live camera taiwan", "AS", "Taipei 101, Taiwan"),
    ("singapore marina bay sands merlion live 4k", "AS", "Singapura - Marina Bay"),
    ("singapore changi airport live cam", "AS", "Singapura - Changi Airport"),
    ("bangkok chao phraya river icon siam live cam", "AS", "Bangkok, Tailândia"),
    ("phuket patong beach bangla road live cam", "AS", "Phuket, Tailândia"),
    ("pattaya beach walking street live webcam", "AS", "Pattaya, Tailândia"),
    ("koh samui chaweng beach live camera 4k", "AS", "Koh Samui, Tailândia"),
    ("bali canggu echo beach live surf cam", "AS", "Bali - Canggu, Indonésia"),
    ("bali kuta beach uluwatu live surf camera", "AS", "Bali - Uluwatu, Indonésia"),
    ("kuala lumpur petronas twin towers live cam", "AS", "Kuala Lumpur, Malásia"),
    ("dubai burj khalifa dubai mall fountain live 4k", "AS", "Dubai - Burj Khalifa, EAU"),
    ("dubai marina jbr beach live camera", "AS", "Dubai - Marina, EAU"),
    ("abu dhabi corniche skyline live camera", "AS", "Abu Dhabi, EAU"),
    ("jerusalem western wall kotel live camera", "AS", "Jerusalém - Muro das Lamentações"),
    ("tel aviv beach promenade live camera", "AS", "Tel Aviv, Israel"),
    ("sydney opera house circular quay live cam 4k", "AS", "Sydney - Opera House, Austrália"),
    ("sydney bondi beach live surf camera 4k", "AS", "Sydney - Bondi Beach, Austrália"),
    ("sydney manly beach live surf camera", "AS", "Sydney - Manly Beach, Austrália"),
    ("melbourne federation square yarra river live cam", "AS", "Melbourne, Austrália"),
    ("gold coast surfers paradise live camera", "AS", "Gold Coast, Austrália"),
    ("brisbane river south bank live camera", "AS", "Brisbane, Austrália"),
    ("auckland viaduct harbour live camera new zealand", "AS", "Auckland, Nova Zelândia"),
    ("queenstown lake wakatipu live camera new zealand", "AS", "Queenstown, Nova Zelândia"),

    # ── AMÉRICA LATINA & ÁFRICA ──
    ("buenos aires obelisco 9 de julio live cam", "AM", "Buenos Aires - Obelisco, Argentina"),
    ("buenos aires puerto madero live camera", "AM", "Buenos Aires - Puerto Madero, Argentina"),
    ("bariloche centro civico lago nahuel huapi live cam", "AM", "Bariloche, Argentina"),
    ("santiago chile san cristobal skyline live cam", "AM", "Santiago, Chile"),
    ("valparaiso vina del mar live beach cam chile", "AM", "Viña del Mar / Valparaíso, Chile"),
    ("lima miraflores larcomar costa verde live cam", "AM", "Lima - Miraflores, Peru"),
    ("cusco plaza de armas live camera peru", "AM", "Cusco, Peru"),
    ("bogota monserrate skyline live camera colombia", "AM", "Bogotá - Monserrate, Colômbia"),
    ("medellin metro plaza botero live cam colombia", "AM", "Medellín, Colômbia"),
    ("cartagena bocagrande walled city live cam colombia", "AM", "Cartagena, Colômbia"),
    ("mexico city zocalo palacio nacional live 4k", "AM", "Cidade do México - Zócalo, México"),
    ("mexico city paseo de la reforma angel independencia live", "AM", "Cidade do México - Reforma, México"),
    ("cancun playa delfines hotel zone live cam", "AM", "Cancún, México"),
    ("playa del carmen 5th avenue live cam mexico", "AM", "Playa del Carmen, México"),
    ("cabo san lucas arch medano beach live cam mexico", "AM", "Cabo San Lucas, México"),
    ("puerto vallarta malecon live camera mexico", "AM", "Puerto Vallarta, México"),
    ("panama canal miraflores locks ships live cam", "AM", "Canal do Panamá, Panamá"),
    ("san jose costa rica live camera", "AM", "Costa Rica"),
    ("punta del este los dedos praia mansa live cam uruguay", "AM", "Punta del Este, Uruguai"),
    ("montevideo rambla pocitos live camera uruguay", "AM", "Montevidéu, Uruguai"),
    ("cape town table mountain waterfront live cam", "AM", "Cidade do Cabo, África do Sul"),
    ("durban beachfront live camera south africa", "AM", "Durban, África do Sul"),
    ("kenya masai mara wildlife waterhole live cam", "AM", "Quênia - Animais Selvagens, África"),
    ("namibia namib desert watering hole live stream", "AM", "Namíbia - Deserto / Animais, África"),
    ("kruger national park live animal safari cam", "AM", "Parque Kruger - Safári ao Vivo, África"),

    # ── CANAIS GLOBAIS, FERROVIAS, AEROPORTOS & ESPAÇO ──
    ("skylinewebcams live webcam stream 24/7", "GL", "SkylineWebcams Global 24/7"),
    ("earthcam live world webcams 4k", "GL", "EarthCam Live Global"),
    ("explore org live ocean animals birds wildlife", "GL", "Explore.org Animais & Oceanos"),
    ("virtual railfan live train stream cam", "US", "Virtual Railfan Ferrovias"),
    ("railstream live train camera 24/7", "US", "Railstream Trens EUA"),
    ("flightradar live airport plane spotting stream", "GL", "Plane Spotting Aeroportos"),
    ("international space station iss nasa live hd", "GL", "Estação Espacial ISS (NASA)"),
    ("aurora borealis northern lights live stream 4k", "GL", "Aurora Boreal ao Vivo"),
    ("volcano live stream kilauea etna popocatepetl", "GL", "Vulcões Ativos ao Vivo"),
]

def search_query_worker(entry) -> List[Dict[str, Any]]:
    query, sector, default_local = entry
    cmd = [
        "/home/douglasdsr/.local/bin/yt-dlp",
        f"ytsearch20:{query}",
        "--flat-playlist",
        "--dump-json",
        "--no-warnings"
    ]
    results = []
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                vid = item.get("id")
                is_live = item.get("is_live") is True or item.get("live_status") == "is_live"
                if vid and is_live:
                    title = item.get("title") or "Câmera ao Vivo"
                    uploader = item.get("uploader") or "Live Stream"
                    
                    results.append({
                        "id": f"cam_yt_{vid}",
                        "nome": title.strip(),
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "setor": sector,
                        "pais": "BR" if sector == "BR" else ("US" if sector == "US" else ("EU" if sector == "EU" else ("JP" if "japão" in default_local.lower() or "tokyo" in default_local.lower() else "INT"))),
                        "local": default_local,
                        "fonte": uploader,
                        "is_real_stream": True,
                        "status": "ONLINE"
                    })
            except Exception:
                continue
    except Exception:
        pass
    return results

def main():
    print("=" * 60)
    print("🚀 INICIANDO MEGA-COLHEITA DE CÂMERAS REAIS AO VIVO")
    print(f"Total de consultas de busca: {len(QUERIES)}")
    print("=" * 60)

    existing_cameras = []
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_cameras = json.load(f)
        except Exception:
            existing_cameras = []

    seen_vids = {c.get("video_id") for c in existing_cameras if c.get("video_id")}
    all_cameras = list(existing_cameras)
    print(f"Câmeras já no banco: {len(all_cameras)}")

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = {executor.submit(search_query_worker, q): q for q in QUERIES}
        completed = 0
        for fut in as_completed(futures):
            q_info = futures[fut]
            completed += 1
            try:
                res = fut.result()
                new_added = 0
                for cam in res:
                    vid = cam["video_id"]
                    if vid not in seen_vids:
                        seen_vids.add(vid)
                        all_cameras.append(cam)
                        new_added += 1
                if completed % 25 == 0 or completed == len(QUERIES):
                    print(f"[{completed}/{len(QUERIES)}] Consultas concluídas -> Total de Câmeras Reais: {len(all_cameras)}")
            except Exception:
                pass

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_cameras, f, ensure_ascii=False, indent=2)

    elapsed = round(time.time() - start_time, 2)
    print("=" * 60)
    print(f"✅ MEGA-COLHEITA CONCLUÍDA EM {elapsed}s!")
    print(f"Total de Câmeras Reais 100% Ao Vivo: {len(all_cameras)}")
    print(f"Salvo em: {OUTPUT_FILE}")
    print("=" * 60)

if __name__ == "__main__":
    main()
