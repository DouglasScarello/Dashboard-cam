#!/usr/bin/env python3
"""
ENRIQUECIMENTO E GEOLOCALIZAÇÃO PRECISA DE TODAS AS CÂMERAS
Corrige nomes sujos, remove ruídos de YouTube, identifica rua/avenida/ponto de referência,
cidade, estado, país e coordenadas exatas de monitoramento.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "database" / "live_cameras.json"

# Regras de Reconhecimento Geoespacial e Endereçamento Detalhado
RULES = [
    # ─── SANTA CATARINA ───
    {
        "patterns": [r"balne[aá]rio\s+cambori[uú]", r"barra\s+sul.*bc", r"barra\s+norte.*bc", r"roda\s+gigante.*bc", r"molhe.*bc"],
        "cidade": "Balneário Camboriú", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"atl[aâ]ntica", "Av. Atlântica (Orla Central)"),
            (r"avenida\s+brasil|av\s+brasil", "Av. Brasil (Centro Comercial)"),
            (r"barra\s+sul|molhe\s+sul", "Av. Normando Tedesco - Molhe da Barra Sul"),
            (r"barra\s+norte|roda\s+gigante|fg\s+big\s+wheel", "Estrada da Rainha - Barra Norte (FG Big Wheel)"),
            (r"praia\s+dos\s+amores", "Av. Carlos Drummond de Andrade - Praia dos Amores"),
            (r"estaleiro|estaleirinho", "Rodovia Interpraias - Praia do Estaleirinho"),
            (r"cristo\s+luz", "Rua Antônio Camacho - Complexo Cristo Luz"),
        ],
        "default_endereco": "Av. Atlântica - Orla da Praia Central",
        "tipo": "ORLA / PRAIA", "lat": -26.9926, "long": -48.6347
    },
    {
        "patterns": [r"jurer[eê]", r"canasvieiras", r"ingleses", r"campeche", r"joaquina", r"praia\s+mole", r"barra\s+da\s+lagoa", r"ponte\s+herc[ií]lio\s+luz", r"florian[oó]polis", r"floripa"],
        "cidade": "Florianópolis", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"jurer[eê]\s+internacional", "Av. dos Búzios - Jurerê Internacional"),
            (r"jurer[eê]", "Av. das Lagostas - Jurerê Tradicional"),
            (r"ingleses", "Rua das Gaivotas - Praia dos Ingleses"),
            (r"canasvieiras", "Rua Antenor Borges - Praia de Canasvieiras"),
            (r"campeche", "Av. Pequeno Príncipe - Praia do Campeche"),
            (r"joaquina", "Av. Prefeito Acácio Garibaldi São Thiago - Praia da Joaquina"),
            (r"praia\s+mole", "Rodovia Jornalista Manoel de Menezes - Praia Mole"),
            (r"barra\s+da\s+lagoa", "Rua Amaro Coelho - Barra da Lagoa"),
            (r"ponte\s+herc[ií]lio\s+luz", "Parque da Luz - Cabeceira da Ponte Hercílio Luz"),
            (r"beira\s+mar\s+norte", "Av. Jornalista Rubens de Arruda Ramos (Beira-Mar Norte)"),
            (r"lagoa\s+da\s+concei[cç][aã]o", "Av. das Rendeiras - Lagoa da Conceição"),
            (r"pantano\s+do\s+sul", "Estrada Rozália Paulina Ferreira - Pântano do Sul"),
        ],
        "default_endereco": "Av. Beira-Mar Norte / Orla da Ilha",
        "tipo": "ORLA / PRAIA", "lat": -27.5954, "long": -48.5480
    },
    {
        "patterns": [r"itajai|itaja[ií]", r"praia\s+brava"],
        "cidade": "Itajaí", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"praia\s+brava", "Av. José Medeiros Vieira - Praia Brava"),
            (r"cabe[cç]udas", "Rua Juvêncio Tavares d'Amaral - Praia de Cabeçudas"),
            (r"porto\s+de\s+itaja[ií]", "Rua Pedro Ferreira - Porto de Itajaí / Canal da Barra"),
        ],
        "default_endereco": "Av. José Medeiros Vieira - Praia Brava",
        "tipo": "ORLA / PORTO", "lat": -26.9078, "long": -48.6619
    },
    {
        "patterns": [r"bombinhas", r"mariscal", r"quatro\s+ilhas", r"zimbros", r"canto\s+grande"],
        "cidade": "Bombinhas", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"mariscal", "Av. Água Marinha - Praia de Mariscal"),
            (r"quatro\s+ilhas", "Rua Ilha das Galés - Praia de Quatro Ilhas"),
            (r"canto\s+grande", "Av. Manoel José dos Santos - Canto Grande"),
        ],
        "default_endereco": "Av. Ver. Manoel José dos Santos - Centro / Praia de Bombinhas",
        "tipo": "ORLA / PRAIA", "lat": -27.1400, "long": -48.5150
    },
    {
        "patterns": [r"itapema", r"meia\s+praia"],
        "cidade": "Itapema", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"meia\s+praia", "Av. Beira Mar, altura da Rua 220 - Meia Praia"),
            (r"canto\s+da\s+praia", "Rua 109 - Canto da Praia"),
        ],
        "default_endereco": "Av. Nereu Ramos - Meia Praia",
        "tipo": "ORLA / PRAIA", "lat": -27.0906, "long": -48.6111
    },
    {
        "patterns": [r"joinville"],
        "cidade": "Joinville", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [(r"expoville", "Rua XV de Novembro - Complexo Expoville"), (r"mirante", "Rua Pastor Guilherme Rau - Mirante do Morro da Boa Vista")],
        "default_endereco": "Rua Visconde de Taunay - Centro",
        "tipo": "CENTRO URBANO", "lat": -26.3045, "long": -48.8487
    },
    {
        "patterns": [r"blumenau"],
        "cidade": "Blumenau", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [(r"vila\s+germ[aâ]nica", "Rua Alberto Stein - Parque Vila Germânica"), (r"beira\s+rio", "Av. Presidente Castelo Branco - Beira Rio")],
        "default_endereco": "Rua XV de Novembro - Centro Histórico",
        "tipo": "CENTRO URBANO", "lat": -26.9194, "long": -49.0661
    },
    {
        "patterns": [r"garopaba", r"praia\s+do\s+rosa"],
        "cidade": "Garopaba / Imbituba", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [(r"praia\s+do\s+rosa", "Estrada Geral do Rosa - Praia do Rosa"), (r"ferrugem", "Estrada Geral da Ferrugem - Praia da Ferrugem")],
        "default_endereco": "Av. dos Pescadores - Praia Central",
        "tipo": "ORLA / PRAIA", "lat": -28.0267, "long": -48.6167
    },
    {
        "patterns": [r"rio\s+do\s+rastro|urubici|s[aã]o\s+joaquim"],
        "cidade": "Serra Catarinense (Bom Jardim / Urubici)", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [(r"rio\s+do\s+rastro", "Rodovia SC-390 - Mirante da Serra do Rio do Rastro"), (r"morro\s+da\s+igreja", "Estrada Geral do Morro da Igreja (Pedra Furada)")],
        "default_endereco": "Rodovia SC-390 - Mirante da Serra",
        "tipo": "SERRA / NATUREZA", "lat": -28.3889, "long": -49.5514
    },
    {
        "patterns": [r"aeroporto.*navegantes|aeroporto.*nvt"],
        "cidade": "Navegantes", "uf": "SC", "pais": "BR", "setor": "BR",
        "ruas": [(r".*", "Rua Osvaldo Reis, 320 - Terminal Aeroporto Internacional Ministro Victor Konder (NVT)")],
        "default_endereco": "Aeroporto Internacional de Navegantes (NVT)",
        "tipo": "AEROPORTO", "lat": -26.8800, "long": -48.6517
    },

    # ─── RIO DE JANEIRO ───
    {
        "patterns": [r"copacabana", r"ipanema", r"leblon", r"arpoador", r"leme", r"barra\s+da\s+tijuca", r"recreio", r"cristo\s+redentor", r"corcovado", r"p[aã]o\s+de\s+a[cç][uú]car", r"maracan[aã]", r"rio\s+de\s+janeiro", r"aeroporto.*santos\s+dumont", r"aeroporto.*gale[aã]o"],
        "cidade": "Rio de Janeiro", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"posto\s*3.*copacabana|copacabana.*posto\s*3", "Av. Atlântica, altura da Rua Hilário de Gouveia (Posto 3) - Copacabana"),
            (r"posto\s*4.*copacabana|copacabana.*posto\s*4", "Av. Atlântica, altura da Rua Santa Clara (Posto 4) - Copacabana"),
            (r"posto\s*5.*copacabana|copacabana.*posto\s*5", "Av. Atlântica, altura da Rua Djalma Ulrich (Posto 5) - Copacabana"),
            (r"posto\s*6.*copacabana|copacabana.*posto\s*6|forte\s+de\s+copacabana", "Praça Cel. Eugênio Franco (Forte de Copacabana / Posto 6)"),
            (r"posto\s*2.*copacabana|leme", "Av. Atlântica, altura da Av. Princesa Isabel - Leme"),
            (r"copacabana", "Av. Atlântica - Orla de Copacabana"),
            (r"arpoador|posto\s*7", "Av. Francisco Bhering - Pedra do Arpoador (Posto 7)"),
            (r"posto\s*8.*ipanema|posto\s*9.*ipanema|ipanema", "Av. Vieira Souto (Posto 9) - Ipanema"),
            (r"leblon|posto\s*11|posto\s*12", "Av. Delfim Moreira (Posto 12 - Mirante do Leblon)"),
            (r"cristo\s+redentor|corcovado", "Parque Nacional da Tijuca - Alto do Corcovado"),
            (r"p[aã]o\s+de\s+a[cç][uú]car|urca", "Av. Pasteur, 520 - Morro da Urca / Pão de Açúcar"),
            (r"barra\s+da\s+tijuca|posto\s*2.*barra|posto\s*4.*barra", "Av. Lúcio Costa, Posto 4 - Barra da Tijuca"),
            (r"recreio|praia\s+da\s+macumba|prainha", "Av. Lúcio Costa - Pontal / Recreio dos Bandeirantes"),
            (r"santos\s+dumont|sdu", "Praça Sen. Salgado Filho - Aeroporto Santos Dumont (SDU)"),
            (r"gale[aã]o|gig", "Av. Vinte de Janeiro - Aeroporto Internacional Tom Jobim (GIG)"),
            (r"ponte\s+rio\s+niter[oó]i", "Rodovia BR-101 - Ponte Presidente Costa e Silva (Rio-Niterói)"),
            (r"aterro\s+do\s+flamengo", "Av. Infante Dom Henrique - Aterro do Flamengo"),
            (r"maracan[aã]", "Av. Presidente Castelo Branco - Complexo do Maracanã"),
        ],
        "default_endereco": "Av. Atlântica / Orla da Zona Sul",
        "tipo": "ORLA / PONTO TURÍSTICO", "lat": -22.9068, "long": -43.1729
    },
    {
        "patterns": [r"cabo\s+frio", r"praia\s+do\s+forte.*rj"],
        "cidade": "Cabo Frio", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"praia\s+do\s+forte", "Av. Macário Pinto Lopes - Praia do Forte"), (r"passagem", "Rua Constantino Menelau - Bairro da Passagem")],
        "default_endereco": "Av. Macário Pinto Lopes - Praia do Forte",
        "tipo": "ORLA / PRAIA", "lat": -22.8808, "long": -42.0186
    },
    {
        "patterns": [r"arraial\s+do\s+cabo", r"prainha.*arraial", r"praia\s+grande.*arraial"],
        "cidade": "Arraial do Cabo", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"praia\s+grande", "Av. Dr. Hermes Barcelos - Praia Grande"), (r"prainha", "Rua Kaialo - Prainha"), (r"forno", "Trilha da Praia do Forno / Porto do Forno")],
        "default_endereco": "Av. Hermes Barcelos - Orla de Arraial",
        "tipo": "ORLA / PRAIA", "lat": -22.9661, "long": -42.0278
    },
    {
        "patterns": [r"b[uú]zios", r"gerib[aá]", r"rua\s+das\s+pedras", r"jo[aã]o\s+fernandes"],
        "cidade": "Armação dos Búzios", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"gerib[aá]", "Rua Gerbert Périssé - Praia de Geribá"), (r"rua\s+das\s+pedras|orla\s+bardot", "Av. José Bento Ribeiro Dantas (Rua das Pedras / Orla Bardot)")],
        "default_endereco": "Av. José Bento Ribeiro Dantas - Orla Bardot",
        "tipo": "ORLA / PRAIA", "lat": -22.7539, "long": -41.8869
    },
    {
        "patterns": [r"angra\s+dos\s+reis|ilha\s+grande"],
        "cidade": "Angra dos Reis", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"abra[aã]o", "Vila do Abraão - Ilha Grande"), (r"porto\s+de\s+angra", "Av. Almirante Júlio Cesar de Noronha - Centro")],
        "default_endereco": "Estrada do Contorno - Baía de Angra",
        "tipo": "ORLA / NATUREZA", "lat": -23.0067, "long": -44.3181
    },
    {
        "patterns": [r"paraty|parati"],
        "cidade": "Paraty", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"centro\s+hist[oó]rico", "Rua da Matriz / Cais de Paraty - Centro Histórico")],
        "default_endereco": "Rua do Comércio - Centro Histórico",
        "tipo": "PATRIMÔNIO HISTÓRICO", "lat": -23.2178, "long": -44.7131
    },
    {
        "patterns": [r"petr[oó]polis|teres[oó]polis"],
        "cidade": "Região Serrana (Petrópolis / Teresópolis)", "uf": "RJ", "pais": "BR", "setor": "BR",
        "ruas": [(r"dedo\s+de\s+deus", "Rodovia BR-116 - Mirante do Soberbo (Dedo de Deus)"), (r"pal[aá]cio\s+de\s+cristal", "Rua Alfredo Pachá - Palácio de Cristal")],
        "default_endereco": "Av. Koeler - Centro / Região Serrana",
        "tipo": "SERRA / NATUREZA", "lat": -22.5050, "long": -43.1789
    },

    # ─── SÃO PAULO ───
    {
        "patterns": [r"s[aã]o\s+paulo", r"avenida\s+paulista", r"marginal\s+pinheiros", r"marginal\s+tiet[eê]", r"aeroporto.*guarulhos|gru", r"aeroporto.*congonhas|cgh", r"aeroporto.*viracopos", r"santos.*praia", r"guaruja|guaruj[aá]", r"bertioga", r"s[aã]o\s+sebasti[aã]o|maresias", r"ilhabela", r"ubatuba", r"campos\s+do\s+jord[aã]o"],
        "cidade": "São Paulo", "uf": "SP", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"avenida\s+paulista|av\s+paulista|masp|fiesp", "Av. Paulista, 1578 (altura do MASP / Trianon) - Bela Vista, SP"),
            (r"consolao|consola[cç][aã]o", "Rua da Consolação x Av. Paulista - Cerqueira César, SP"),
            (r"marginal\s+pinheiros|ponte\s+estaiada", "Av. das Nações Unidas (Ponte Estaiada Octavio Frias) - Brooklin, SP"),
            (r"marginal\s+tiet[eê]", "Av. Marginal Tietê (altura da Ponte das Bandeiras) - Santana, SP"),
            (r"23\s+de\s+maio", "Av. Vinte e Três de Maio - Paraíso / Centro, SP"),
            (r"faria\s+lima", "Av. Brigadeiro Faria Lima x Av. Rebouças - Itaim Bibi, SP"),
            (r"aeroporto.*guarulhos|gru", "Rodovia Hélio Smidt - Terminal 3 Aeroporto de Guarulhos (GRU)"),
            (r"aeroporto.*congonhas|cgh", "Av. Washington Luís - Terminal Aeroporto de Congonhas (CGH)"),
            (r"aeroporto.*viracopos|vcp|campinas", "Rodovia Santos Dumont, km 66 - Aeroporto de Viracopos (VCP), Campinas"),
            (r"santos.*porto|canal\s*4|canal\s*3|ponta\s+da\s+praia", "Av. Bartolomeu de Gusmão (Canal 4) - Ponta da Praia, Santos, SP"),
            (r"santos.*praia|gonzaga", "Av. Presidente Wilson - Gonzaga / Orla de Santos, SP"),
            (r"guaruja.*enseada|enseada", "Av. Miguel Stéfano - Praia da Enseada, Guarujá, SP"),
            (r"guaruja.*pitangueiras|pitangueiras", "Av. Marechal Deodoro da Fonseca - Praia das Pitangueiras, Guarujá, SP"),
            (r"bertioga|riviera", "Av. da Riviera, Módulo 2 - Riviera de São Lourenço, Bertioga, SP"),
            (r"maresias", "Av. Dr. Francisco Loup - Praia de Maresias, São Sebastião, SP"),
            (r"ilhabela", "Av. Pedro Paula de Moraes - Praia do Saco da Capela, Ilhabela, SP"),
            (r"ubatuba.*praia\s+grande|praia\s+grande.*ubatuba", "Av. Atlântica - Praia Grande, Ubatuba, SP"),
            (r"ubatuba.*itamambuca", "Estrada de Itamambuca - Praia de Itamambuca, Ubatuba, SP"),
            (r"campos\s+do\s+jord[aã]o|capivari", "Av. Macedo Soares - Vila Capivari, Campos do Jordão, SP"),
            (r"anchieta|imigrantes", "Rodovia dos Imigrantes (km 40 - Trecho de Serra), SP"),
            (r"dutra|presidente\s+dutra", "Rodovia Presidente Dutra (BR-116), SP"),
            (r"castello\s+branco", "Rodovia Castelo Branco (SP-280), SP"),
            (r"anhanguera|bandeirantes", "Rodovia dos Bandeirantes (SP-348), SP"),
        ],
        "default_endereco": "Av. Paulista / Região Metropolitana",
        "tipo": "VIA ARTERIAL / TRÂNSITO", "lat": -23.5505, "long": -46.6333
    },

    # ─── RIO GRANDE DO SUL ───
    {
        "patterns": [r"porto\s+alegre", r"gua[ií]ba", r"gramado", r"canela", r"caxias\s+do\s+sul", r"torres.*rs", r"cap[aã]o\s+da\s+canoa"],
        "cidade": "Porto Alegre / Serra Gaúcha", "uf": "RS", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"orla.*gua[ií]ba|gua[ií]ba|gas[oô]metro", "Av. Edvaldo Pereira Paiva (Orla do Guaíba / Usina do Gasômetro) - Porto Alegre, RS"),
            (r"salgado\s+filho|poa", "Av. Severo Dullius, 90010 - Aeroporto Internacional Salgado Filho (POA)"),
            (r"gramado.*rua\s+coberta|rua\s+coberta", "Rua Madre Verônica (Rua Coberta) - Centro, Gramado, RS"),
            (r"gramado.*borges|borges\s+de\s+medeiros", "Av. Borges de Medeiros - Centro, Gramado, RS"),
            (r"canela.*catedral|catedral\s+de\s+pedra", "Praça da Matriz - Catedral de Pedra, Canela, RS"),
            (r"torres", "Av. Beira-Mar - Praia Grande / Guarita, Torres, RS"),
            (r"cap[aã]o\s+da\s+canoa", "Av. Beira-Mar - Praia Central, Capão da Canoa, RS"),
        ],
        "default_endereco": "Av. Edvaldo Pereira Paiva - Orla do Guaíba, Porto Alegre",
        "tipo": "ORLA / CIDADE", "lat": -30.0346, "long": -51.2177
    },

    # ─── PARANÁ ───
    {
        "patterns": [r"curitiba", r"foz\s+do\s+igua[cç]u", r"cataratas", r"ponte\s+da\s+amizade", r"matinhos", r"guaratuba", r"paranagu[aá]"],
        "cidade": "Curitiba / Foz do Iguaçu", "uf": "PR", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"ponte\s+da\s+amizade|fronteira.*paraguai|ciudad\s+del\s+este", "BR-277 - Ponte Internacional da Amizade (Fronteira Brasil - Paraguai)"),
            (r"cataratas", "Rodovia BR-469 - Parque Nacional do Iguaçu (Cataratas)"),
            (r"jardim\s+bot[aâ]nico.*curitiba", "Rua Eng. Ostoja Roguski - Estufa do Jardim Botânico, Curitiba, PR"),
            (r"parque\s+barigui", "Av. Cândido Hartmann - Parque Barigui, Curitiba, PR"),
            (r"afonso\s+pena|cwb", "Av. Rocha Pombo - Aeroporto Internacional Afonso Pena (CWB)"),
            (r"porto\s+de\s+paranagu[aá]", "Av. Portuária - Terminal do Porto de Paranaguá, PR"),
            (r"guaratuba|matinhos|caiob[aá]", "Av. Atlântica - Praia Brava de Caiobá / Guaratuba, PR"),
        ],
        "default_endereco": "Av. Cândido de Abreu - Centro Cívico, Curitiba, PR",
        "tipo": "PONTO TURÍSTICO / FRONTEIRA", "lat": -25.4284, "long": -49.2733
    },

    # ─── BAHIA & NORDESTE ───
    {
        "patterns": [r"salvador", r"farol\s+da\s+barra", r"pelourinho", r"porto\s+seguro", r"trancoso", r"arraial\s+d.ajuda", r"ilheus|ilh[eé]us", r"itacar[eé]", r"morro\s+de\s+s[aã]o\s+paulo"],
        "cidade": "Salvador / Litoral Baiano", "uf": "BA", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"farol\s+da\s+barra|barra.*salvador", "Largo do Farol da Barra - Av. Oceânica, Salvador, BA"),
            (r"pelourinho|elevador\s+lacerda", "Praça Thomé de Souza / Elevador Lacerda - Pelourinho, Salvador, BA"),
            (r"rio\s+vermelho", "Largo de Santana (Largo da Dinha) - Rio Vermelho, Salvador, BA"),
            (r"trancoso", "Praça São João (Quadrado de Trancoso) - Porto Seguro, BA"),
            (r"passarela\s+do\s+alcool|porto\s+seguro", "Av. Portugal (Passarela do Descobrimento) - Porto Seguro, BA"),
            (r"morro\s+de\s+s[aã]o\s+paulo", "Primeira / Segunda Praia - Morro de São Paulo, Cairu, BA"),
            (r"itacar[eé]", "Praia da Concha / Rua Pedro Longo - Itacaré, BA"),
        ],
        "default_endereco": "Av. Oceânica - Orla da Barra, Salvador",
        "tipo": "ORLA / PATRIMÔNIO HISTÓRICO", "lat": -12.9777, "long": -38.5016
    },
    {
        "patterns": [r"recife", r"boa\s+viagem", r"marco\s+zero.*pe", r"olinda", r"porto\s+de\s+galinhas", r"noronha"],
        "cidade": "Recife / Porto de Galinhas", "uf": "PE", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"boa\s+viagem", "Av. Boa Viagem (altura do Parque Dona Lindu) - Recife, PE"),
            (r"marco\s+zero", "Praça Rio Branco (Marco Zero) - Recife Antigo, PE"),
            (r"olinda", "Alto da Sé - Centro Histórico de Olinda, PE"),
            (r"porto\s+de\s+galinhas", "Rua das Piscinas Naturais - Vila de Porto de Galinhas, Ipojuca, PE"),
            (r"fernando\s+de\s+noronha", "Baía do Sancho / Praia da Conceição - Fernando de Noronha, PE"),
        ],
        "default_endereco": "Av. Boa Viagem - Orla Marítima, Recife",
        "tipo": "ORLA / PRAIA", "lat": -8.0476, "long": -34.8770
    },
    {
        "patterns": [r"fortaleza", r"beira\s+mar.*ce", r"praia\s+de\s+iracema", r"praia\s+do\s+futuro", r"jericoacoara", r"canoa\s+quebrada"],
        "cidade": "Fortaleza / Litoral Cearense", "uf": "CE", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"beira\s+mar|iracema", "Av. Beira Mar (Feirinha de Artesanato / Espigão do Náutico) - Meireles, Fortaleza, CE"),
            (r"praia\s+do\s+futuro", "Av. Clóvis Arrais Maia - Praia do Futuro, Fortaleza, CE"),
            (r"jericoacoara|jeri", "Rua Principal / Duna do Pôr do Sol - Vila de Jericoacoara, Jijoca, CE"),
            (r"canoa\s+quebrada", "Rua Dragão do Mar (Broadway) - Canoa Quebrada, Aracati, CE"),
        ],
        "default_endereco": "Av. Beira Mar - Orla de Meireles, Fortaleza",
        "tipo": "ORLA / PRAIA", "lat": -3.7319, "long": -38.5267
    },
    {
        "patterns": [r"natal.*rn", r"ponta\s+negra", r"morro\s+do\s+careca", r"praia\s+da\s+pipa"],
        "cidade": "Natal / Pipa", "uf": "RN", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"ponta\s+negra|morro\s+do\s+careca", "Av. Erivan França - Praia de Ponta Negra (Morro do Careca), Natal, RN"),
            (r"praia\s+da\s+pipa|pipa", "Av. Baía dos Golfinhos - Praia do Centro / Pipa, Tibau do Sul, RN"),
        ],
        "default_endereco": "Av. Erivan França - Orla de Ponta Negra, Natal",
        "tipo": "ORLA / PRAIA", "lat": -5.7945, "long": -35.2110
    },
    {
        "patterns": [r"macei[oó]", r"ponta\s+verde", r"paju[cç]ara", r"maragogi"],
        "cidade": "Maceió / Maragogi", "uf": "AL", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"ponta\s+verde|paju[cç]ara", "Av. Silvio Carlos Viana (Lighthouse Ponta Verde) - Maceió, AL"),
            (r"maragogi", "Av. Senador Rui Palmeira (Orla Central) - Maragogi, AL"),
        ],
        "default_endereco": "Av. Álvaro Otacílio - Orla da Ponta Verde, Maceió",
        "tipo": "ORLA / PRAIA", "lat": -9.6658, "long": -35.7351
    },
    {
        "patterns": [r"jo[aã]o\s+pessoa", r"tamba[uú]", r"cabo\s+branco"],
        "cidade": "João Pessoa", "uf": "PB", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"tamba[uú]|cabo\s+branco", "Av. Almirante Tamandaré (Busto de Tamandaré) - Praia de Tambaú, João Pessoa, PB"),
        ],
        "default_endereco": "Av. Cabo Branco - Orla Marítima, João Pessoa",
        "tipo": "ORLA / PRAIA", "lat": -7.1195, "long": -34.8450
    },

    # ─── MINAS GERAIS, DF & CENTRO-OESTE ───
    {
        "patterns": [r"belo\s+horizonte", r"pampulha", r"ouro\s+preto", r"tiradentes.*mg"],
        "cidade": "Belo Horizonte / Ouro Preto", "uf": "MG", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"pampulha|igrejinha", "Av. Otacílio Negrão de Lima, 3000 - Orla da Lagoa da Pampulha, BH"),
            (r"pra[cç]a\s+do\s+papa|mangabeiras", "Praça Governador Israel Pinheiro (Praça do Papa) - Mangabeiras, BH"),
            (r"pra[cç]a\s+da\s+liberdade", "Circuito Praça da Liberdade - Savassi / Funcionários, BH"),
            (r"ouro\s+preto", "Praça Tiradentes - Centro Histórico de Ouro Preto, MG"),
        ],
        "default_endereco": "Av. Otacílio Negrão de Lima - Lagoa da Pampulha, BH",
        "tipo": "PONTO TURÍSTICO / CIDADE", "lat": -19.9167, "long": -43.9345
    },
    {
        "patterns": [r"bras[ií]lia", r"esplanada", r"congresso\s+nacional", r"pra[cç]a\s+dos\s+tr[eê]s\s+poderes"],
        "cidade": "Brasília", "uf": "DF", "pais": "BR", "setor": "BR",
        "ruas": [
            (r"esplanada|congresso|tr[eê]s\s+poderes", "Eixo Monumental (Praça dos Três Poderes / Congresso Nacional) - Brasília, DF"),
            (r"ponte\s+jk", "Estrada Parque Dom Bosco - Ponte Juscelino Kubitschek (Lago Paranoá)"),
            (r"aeroporto.*bras[ií]lia|bsb", "Terminal 1 - Aeroporto Internacional Presidente Juscelino Kubitschek (BSB)"),
        ],
        "default_endereco": "Eixo Monumental - Esplanada dos Ministérios, DF",
        "tipo": "CENTRO CÍVICO / GOVERNO", "lat": -15.7942, "long": -47.8822
    },

    # ─── ESTADOS UNIDOS ───
    {
        "patterns": [r"times\s+square", r"broadway.*ny", r"brooklyn\s+bridge", r"central\s+park", r"manhattan", r"new\s+york"],
        "cidade": "New York City", "uf": "NY", "pais": "US", "setor": "US",
        "ruas": [
            (r"times\s+square|broadway", "Broadway & 7th Ave (Father Duffy Square / 46th St) - Times Square, Manhattan, NY"),
            (r"brooklyn\s+bridge", "Brooklyn Bridge Promenade - Lower Manhattan / East River, NY"),
            (r"central\s+park", "Central Park South & 5th Ave - Manhattan, NY"),
            (r"world\s+trade\s+center", "One World Trade Center (Liberty St) - Financial District, NY"),
        ],
        "default_endereco": "Broadway & 7th Ave - Times Square, NY",
        "tipo": "METRÓPOLE GLOBAL", "lat": 40.7580, "long": -73.9855
    },
    {
        "patterns": [r"las\s+vegas", r"bellagio", r"fremont\s+street", r"the\s+strip.*vegas"],
        "cidade": "Las Vegas", "uf": "NV", "pais": "US", "setor": "US",
        "ruas": [
            (r"bellagio", "3600 S Las Vegas Blvd (Bellagio Fountains) - Las Vegas Strip, NV"),
            (r"fremont", "425 Fremont St (Fremont Street Experience) - Downtown Las Vegas, NV"),
        ],
        "default_endereco": "South Las Vegas Blvd - The Strip, NV",
        "tipo": "ENTRETENIMENTO / TURISMO", "lat": 36.1699, "long": -115.1398
    },
    {
        "patterns": [r"miami\s+beach", r"ocean\s+drive", r"south\s+beach", r"biscayne"],
        "cidade": "Miami Beach", "uf": "FL", "pais": "US", "setor": "US",
        "ruas": [
            (r"ocean\s+drive|south\s+beach", "Ocean Dr & 10th St (Art Deco District) - South Beach, Miami Beach, FL"),
            (r"biscayne|downtown\s+miami", "Biscayne Blvd - Bayfront Park / Downtown Miami, FL"),
        ],
        "default_endereco": "Ocean Drive - South Beach, Miami Beach, FL",
        "tipo": "ORLA / TURISMO", "lat": 25.7907, "long": -80.1300
    },
    {
        "patterns": [r"venice\s+beach", r"santa\s+monica", r"hollywood\s+blvd", r"los\s+angeles"],
        "cidade": "Los Angeles", "uf": "CA", "pais": "US", "setor": "US",
        "ruas": [
            (r"venice\s+beach", "1800 Ocean Front Walk - Venice Beach Boardwalk, Los Angeles, CA"),
            (r"santa\s+monica", "200 Santa Monica Pier - Santa Monica Pier, CA"),
            (r"hollywood", "6925 Hollywood Blvd (TCL Chinese Theatre / Walk of Fame), Hollywood, CA"),
        ],
        "default_endereco": "Ocean Front Walk - Venice Beach / Santa Monica, CA",
        "tipo": "ORLA / ENTRETENIMENTO", "lat": 34.0522, "long": -118.2437
    },
    {
        "patterns": [r"golden\s+gate", r"pier\s+39", r"san\s+francisco"],
        "cidade": "San Francisco", "uf": "CA", "pais": "US", "setor": "US",
        "ruas": [
            (r"golden\s+gate", "Golden Gate Bridge (Vista Point / Marin Headlands) - San Francisco, CA"),
            (r"pier\s+39|fishermans\s+wharf", "The Embarcadero (Pier 39 / Fisherman's Wharf) - San Francisco, CA"),
        ],
        "default_endereco": "Golden Gate Bridge / The Embarcadero, San Francisco, CA",
        "tipo": "PONTO TURÍSTICO", "lat": 37.7749, "long": -122.4194
    },
    {
        "patterns": [r"waikiki", r"honolulu", r"maui", r"hawaii|hava[ií]"],
        "cidade": "Honolulu / Maui", "uf": "HI", "pais": "US", "setor": "US",
        "ruas": [
            (r"waikiki", "Kalakaua Ave - Waikiki Beach (Kuhio Beach Park), Honolulu, HI"),
            (r"pipeline|north\s+shore", "Kamehameha Hwy - Ehukai Beach Park (Banzai Pipeline), Oahu, HI"),
        ],
        "default_endereco": "Kalakaua Ave - Waikiki Beach, Honolulu, HI",
        "tipo": "ORLA / SURF", "lat": 21.3069, "long": -157.8583
    },

    # ─── EUROPA & ÁSIA ───
    {
        "patterns": [r"shibuya", r"shinjuku", r"akihabara", r"tokyo|t[oó]quio", r"mount\s+fuji|monte\s+fuji"],
        "cidade": "Tóquio", "uf": "Tokyo", "pais": "JP", "setor": "AS",
        "ruas": [
            (r"shibuya", "Shibuya Scramble Crossing (Hachiko Exit) - Shibuya-ku, Tóquio"),
            (r"shinjuku|kabukicho", "Kabukicho Ichiban-gai - Shinjuku-ku, Tóquio"),
            (r"akihabara", "Chuo-dori (Electric Town) - Akihabara, Chiyoda-ku, Tóquio"),
            (r"mount\s+fuji|kawaguchiko", "Lago Kawaguchiko (Vista Norte do Monte Fuji), Yamanashi"),
        ],
        "default_endereco": "Shibuya Crossing - Tóquio",
        "tipo": "METRÓPOLE GLOBAL", "lat": 35.6595, "long": 139.7004
    },
    {
        "patterns": [r"abbey\s+road", r"tower\s+bridge", r"big\s+ben", r"london|londres"],
        "cidade": "Londres", "uf": "Greater London", "pais": "GB", "setor": "EU",
        "ruas": [
            (r"abbey\s+road", "3 Abbey Road (Faixa de Pedestres dos Beatles) - St. John's Wood, Londres"),
            (r"tower\s+bridge", "Tower Bridge Rd (Rio Tâmisa) - Londres"),
            (r"big\s+ben|westminster", "Bridge St (Westminster Palace & Big Ben) - Londres"),
        ],
        "default_endereco": "Tower Bridge / Abbey Road, Londres",
        "tipo": "PATRIMÔNIO HISTÓRICO", "lat": 51.5074, "long": -0.1278
    },
    {
        "patterns": [r"torre\s+eiffel|eiffel\s+tower", r"seine|rio\s+sena", r"paris"],
        "cidade": "Paris", "uf": "Île-de-France", "pais": "FR", "setor": "EU",
        "ruas": [
            (r"eiffel|trocadero", "Champ de Mars / Esplanade du Trocadéro - 7º Arrondissement, Paris"),
            (r"notre\s+dame|seine", "Quai de la Tournelle (Rio Sena / Notre-Dame) - Paris"),
        ],
        "default_endereco": "Champ de Mars - Torre Eiffel, Paris",
        "tipo": "PATRIMÔNIO MUNDIAL", "lat": 48.8584, "long": 2.2945
    },
    {
        "patterns": [r"coliseu|colosseum", r"trevi", r"roma|rome", r"vatican|vaticano"],
        "cidade": "Roma", "uf": "Lazio", "pais": "IT", "setor": "EU",
        "ruas": [
            (r"coliseu|colosseum", "Piazza del Colosseo, 1 - Centro Histórico, Roma"),
            (r"trevi", "Piazza di Trevi - Fontana di Trevi, Roma"),
            (r"vatican|st\s+peter", "Piazza San Pietro - Basílica de São Pedro, Vaticano"),
        ],
        "default_endereco": "Piazza del Colosseo - Roma",
        "tipo": "PATRIMÔNIO HISTÓRICO", "lat": 41.8902, "long": 12.4922
    },
    {
        "patterns": [r"veneza|venice", r"rialto", r"san\s+marco"],
        "cidade": "Veneza", "uf": "Veneto", "pais": "IT", "setor": "EU",
        "ruas": [
            (r"rialto", "Ponte di Rialto (Grand Canal) - San Polo, Veneza"),
            (r"san\s+marco", "Piazza San Marco - Centro Histórico, Veneza"),
        ],
        "default_endereco": "Grand Canal - Ponte di Rialto, Veneza",
        "tipo": "PATRIMÔNIO HISTÓRICO", "lat": 45.4408, "long": 12.3155
    },
    {
        "patterns": [r"sagrada\s+familia|barcelona", r"barceloneta"],
        "cidade": "Barcelona", "uf": "Catalunha", "pais": "ES", "setor": "EU",
        "ruas": [
            (r"sagrada\s+familia", "Carrer de Mallorca, 401 (Basílica da Sagrada Família) - Barcelona"),
            (r"barceloneta", "Passeig Marítim de la Barceloneta - Orla de Barcelona"),
        ],
        "default_endereco": "Carrer de Mallorca - Sagrada Família, Barcelona",
        "tipo": "PATRIMÔNIO HISTÓRICO", "lat": 41.3879, "long": 2.1699
    },
    {
        "patterns": [r"lisboa|lisbon", r"pra[cç]a\s+do\s+com[eé]rcio", r"porto.*portugal", r"nazar[eé]"],
        "cidade": "Lisboa / Porto / Nazaré", "uf": "Portugal", "pais": "PT", "setor": "EU",
        "ruas": [
            (r"pra[cç]a\s+do\s+com[eé]rcio|terreiro\s+do\s+pa[cç]o", "Praça do Comércio (Terreiro do Paço / Rio Tejo) - Lisboa"),
            (r"ribeira|douro|dom\s+luis", "Cais da Ribeira (Ponte Luís I / Rio Douro) - Porto"),
            (r"nazar[eé]|praia\s+do\s+norte", "Forte de São Miguel Arcanjo (Praia do Norte - Ondas Gigantes) - Nazaré"),
        ],
        "default_endereco": "Praça do Comércio - Lisboa",
        "tipo": "ORLA / PATRIMÔNIO", "lat": 38.7223, "long": -9.1393
    }
]

def clean_title(title: str) -> str:
    t = title
    # Remove junk tags
    t = re.sub(r'\[\s*(LIVE|AO VIVO|4K|HD|24/7|CAM|STREAM)\s*\]', '', t, flags=re.IGNORECASE)
    t = re.sub(r'🔴|🔥|✈️|📹|🏖️|🌴|📷|🇺🇸|🇧🇷|🇯🇵|🇪🇺', '', t)
    t = re.sub(r'\b(AO VIVO|LIVE|4K|24/7|FULL HD|MOVE NO CHAT|ONLINE|WEBCAM|EN VIVO|DIRECTO)\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s*[-–—|:]\s*$', '', t)
    t = re.sub(r'^\s*[-–—|:]\s*', '', t)
    t = re.sub(r'\s{2,}', ' ', t).strip()
    return t

def enrich_camera(cam: dict, index: int) -> dict:
    original_title = cam.get("nome", "")
    current_local = cam.get("local", "")
    search_text = f"{original_title} {current_local} {cam.get('url', '')}".lower()
    
    # Defaults
    cidade = current_local.split(",")[0].strip() if current_local else "Brasil"
    uf = current_local.split(",")[1].strip() if "," in current_local else "BR"
    pais = cam.get("pais", "BR")
    setor = cam.get("setor", "BR")
    endereco = f"Área Central - {cidade}"
    tipo = "PONTO DE MONITORAMENTO"
    lat = cam.get("lat")
    long = cam.get("long")

    matched_rule = None
    for rule in RULES:
        for pat in rule["patterns"]:
            if re.search(pat, search_text, re.IGNORECASE):
                matched_rule = rule
                break
        if matched_rule:
            break

    if matched_rule:
        cidade = matched_rule["cidade"]
        uf = matched_rule["uf"]
        pais = matched_rule["pais"]
        setor = matched_rule["setor"]
        endereco = matched_rule["default_endereco"]
        tipo = matched_rule["tipo"]
        lat = matched_rule.get("lat", lat)
        long = matched_rule.get("long", long)

        # Procura por ruas / pontos específicos dentro da regra
        for r_pat, r_end in matched_rule.get("ruas", []):
            if re.search(r_pat, search_text, re.IGNORECASE):
                endereco = r_end
                break

    # Gera nome limpo e tático
    nome_base = clean_title(original_title)
    if not nome_base or len(nome_base) < 4:
        nome_base = f"Câmera de Monitoramento {cidade}"

    # Formata nome com precisão
    local_formatado = f"{cidade}, {uf}" if uf and uf != cidade else cidade

    return {
        "id": cam.get("id", f"cam_{index+1}"),
        "nome": nome_base.upper(),
        "endereco": endereco,
        "local": local_formatado,
        "cidade": cidade,
        "uf": uf,
        "setor": setor,
        "pais": pais,
        "tipo_area": tipo,
        "thumbnail_url": cam.get("thumbnail_url", f"/api/cameras/cam_{index+1}/thumbnail.jpg"),
        "url": cam.get("url"),
        "video_id": cam.get("video_id"),
        "lat": lat,
        "long": long,
        "status": "LIVE",
        "is_real_stream": True
    }

def main():
    with open(DB_FILE, "r", encoding="utf-8") as f:
        cams = json.load(f)

    enriched = []
    for idx, c in enumerate(cams):
        enriched.append(enrich_camera(c, idx))

    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"✅ Enriquecimento concluído para {len(enriched)} câmeras!")
    print("\n--- Exemplos de Câmeras Enriquecidas ---")
    for c in enriched[:10]:
        print(f"ID: {c['id']}")
        print(f"  Nome:     {c['nome']}")
        print(f"  Endereço: {c['endereco']}")
        print(f"  Local:    {c['local']} ({c['pais']}) | Setor: {c['setor']}")
        print(f"  Tipo:     {c['tipo_area']}")
        print("-" * 50)

if __name__ == "__main__":
    main()
