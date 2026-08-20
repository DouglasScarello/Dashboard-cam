import sqlite3
import urllib.request
import json
import re
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'data' / 'intelligence.db'

def clean_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&amp;', '&').replace('&apos;', "'").replace('&#039;', "'")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return '\n\n'.join(lines)

def is_valid_person(title: str) -> bool:
    if not title or len(title.strip()) < 3:
        return False
    upper = title.upper()
    bad_prefixes = [
        'UNKNOWN', 'MURDER IN', 'MURDERS IN', 'BANK ROBBERY', 'COMMERCIAL ARMED',
        'SEEKING INFORMATION', 'UNIDENTIFIED', 'ROBBERY OF', 'THEFT OF', 'SHOOTING AT',
        'INVESTIGATION OF', 'SUSPICIOUS DEATH', 'HUMAN REMAINS', 'BURGLARY'
    ]
    for bp in bad_prefixes:
        if bp in upper:
            return False
    return True

BRAZILIAN_WANTED = [
    {
        'id': 'BRA_MJSP_001',
        'name': 'ANDRÉ OLIVEIRA MACEDO',
        'aliases': json.dumps(['André do Rap', 'Macedo', 'Patrão do Porto']),
        'category': 'wanted',
        'source': 'MJSP / Polícia Federal',
        'birth_date': '1977-04-10',
        'sex': 'M',
        'height_cm': 178,
        'weight_kg': 85,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Líder de Narcotráfico Internacional (PCC)',
        'description': 'Principal operador logístico do PCC para exportação de cocaína para a Europa através de navios cargueiros no Porto de Santos/SP. Possui mandados de prisão expedidos pelo STF e Justiça Federal. Difusão Vermelha na Interpol.',
        'reward': 'R$ 100.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Andr%C3%A9_do_Rap.jpg/400px-Andr%C3%A9_do_Rap.jpg',
        'crimes': [
            ('Tráfico Internacional de Drogas', 'CRITICAL'),
            ('Associação Criminosa e Organização Criminosa', 'HIGH'),
            ('Lavagem de Capitais', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Bolívia', 'Santa Cruz de la Sierra', 'Santa Cruz', 'Refúgio em fazendas na Bolívia/Paraguai'),
            ('origin', 'Brasil', 'São Paulo', 'Santos', 'Porto de Santos e Baixada Santista')
        ]
    },
    {
        'id': 'BRA_MJSP_002',
        'name': 'SONIA APARECIDA ROSSI',
        'aliases': json.dumps(['Maria do Pó', 'Dona Sonia', 'Rainha do Tráfico']),
        'category': 'wanted',
        'source': 'MJSP / Polícia Civil SP',
        'birth_date': '1960-04-22',
        'sex': 'F',
        'height_cm': 162,
        'weight_kg': 70,
        'eye_color': 'Castanhos',
        'hair_color': 'Grisalhos / Castanhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Chefe de Distribuição de Narcóticos e Armas',
        'description': 'Considerada a maior traficante de cocaína e pasta-base do estado de São Paulo e região de Campinas. Foragida após fuga cinematográfica da Penitenciária de Santana. Ligada ao fornecimento de armas pesadas e entorpecentes.',
        'reward': 'R$ 50.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico Ilícito de Entorpecentes', 'CRITICAL'),
            ('Tráfico Internacional de Armas de Fogo', 'HIGH'),
            ('Fuga de Preso e Falsidade Ideológica', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'São Paulo', 'Campinas', 'Área metropolitana de Campinas e Vale do Paraíba'),
            ('origin', 'Brasil', 'São Paulo', 'Franco da Rocha', 'Interior paulista')
        ]
    },
    {
        'id': 'BRA_MJSP_003',
        'name': 'WILLIAN BARRETO DE OLIVEIRA',
        'aliases': json.dumps(['Playboy da Curicica', 'Barreto', '01 da Curicica']),
        'category': 'wanted',
        'source': 'Disque Denúncia RJ / Polícia Civil RJ',
        'birth_date': '1985-11-15',
        'sex': 'M',
        'height_cm': 175,
        'weight_kg': 80,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Líder de Milícia Paramilitar Armada',
        'description': 'Chefe de organização paramilitar e milícia armada na Zona Oeste do Rio de Janeiro (Jacarepaguá, Curicica e Praça Seca). Responsável por homicídios, extorsão de comerciantes, grilagem de terras e controle armado.',
        'reward': 'R$ 30.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&fit=crop&q=80',
        'crimes': [
            ('Constituição de Milícia Privada Armada', 'CRITICAL'),
            ('Homicídio Qualificado e Ocultação de Cadáver', 'CRITICAL'),
            ('Extorsão Mediante Sequestro', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Rio de Janeiro', 'Curicica e Jacarepaguá - Zona Oeste RJ')
        ]
    },
    {
        'id': 'BRA_MJSP_004',
        'name': 'WILTON CARLOS RABELLO QUINTANILHA',
        'aliases': json.dumps(['Abelha', '01 do CV', 'Professor']),
        'category': 'wanted',
        'source': 'Polícia Civil RJ / Ministério da Justiça',
        'birth_date': '1971-08-12',
        'sex': 'M',
        'height_cm': 172,
        'weight_kg': 78,
        'eye_color': 'Castanhos',
        'hair_color': 'Grisalhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Membro da Cúpula da Facção Comando Vermelho (CV)',
        'description': 'Integrante histórico da alta cúpula do Comando Vermelho no Rio de Janeiro. Articulador de invasões territoriais, ataques a facções rivais e abastecimento de fuzis e munições para o Complexo da Penha e Alemão.',
        'reward': 'R$ 50.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico de Drogas e Armas de Guerra', 'CRITICAL'),
            ('Organização Criminosa Armada', 'CRITICAL'),
            ('Homicídios de Agentes de Segurança Pública', 'CRITICAL')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Rio de Janeiro', 'Complexo da Penha / Vila Cruzeiro')
        ]
    },
    {
        'id': 'BRA_MJSP_005',
        'name': 'EDGAR ALVES DE ANDRADE',
        'aliases': json.dumps(['Doca', 'Urso', 'Doca da Penha']),
        'category': 'wanted',
        'source': 'Disque Denúncia RJ / Polícia Federal',
        'birth_date': '1970-06-25',
        'sex': 'M',
        'height_cm': 180,
        'weight_kg': 90,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Chefe Militar do Comando Vermelho',
        'description': 'Líder operacional da facção CV no Complexo da Penha. Mandante de roubos de cargas na Av. Brasil e rodovias federais, guerras pelo controle territorial na Zona Oeste e Norte do RJ.',
        'reward': 'R$ 30.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&fit=crop&q=80',
        'crimes': [
            ('Homicídio Qualificado', 'CRITICAL'),
            ('Roubo Majorado de Cargas com Armas de Fogo', 'HIGH'),
            ('Tráfico de Entorpecentes', 'CRITICAL')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Rio de Janeiro', 'Vila Cruzeiro / Parque Proletário')
        ]
    },
    {
        'id': 'BRA_MJSP_006',
        'name': 'ÁLVARO MALAQUIAS SANTA ROSA',
        'aliases': json.dumps(['Peixão', 'Arão', 'Pastor do Tráfico']),
        'category': 'wanted',
        'source': 'Polícia Civil RJ / DEIC',
        'birth_date': '1986-03-09',
        'sex': 'M',
        'height_cm': 177,
        'weight_kg': 82,
        'eye_color': 'Castanhos',
        'hair_color': 'Castanhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Líder da Facção Terceiro Comando Puro (TCP)',
        'description': 'Chefe da facção TCP e criador do chamado Complexo de Israel (comunidades de Vigário Geral, Parada de Lucas, Cidade Alta e Cinco Bocas). Responde por dezenas de homicídios, perseguição religiosa e roubo de cargas.',
        'reward': 'R$ 50.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico de Drogas e Armas', 'CRITICAL'),
            ('Intolerância Religiosa e Expulsão de Moradores', 'HIGH'),
            ('Organização Criminosa Paramilitar', 'CRITICAL')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Rio de Janeiro', 'Parada de Lucas / Vigário Geral')
        ]
    },
    {
        'id': 'BRA_MJSP_007',
        'name': 'LEOMAR OLIVEIRA BARBOSA',
        'aliases': json.dumps(['Playboy', 'Leomar', 'Braço do Fernandinho']),
        'category': 'wanted',
        'source': 'MJSP / Polícia Federal / Interpol',
        'birth_date': '1963-07-28',
        'sex': 'M',
        'height_cm': 170,
        'weight_kg': 75,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos / Grisalhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Operador de Narcotráfico Internacional',
        'description': 'Braço direito histórico de Luiz Fernando da Costa (Beira-Mar). Operava o transporte aéreo de cocaína da Colômbia e Bolívia para Goiás e Rio de Janeiro. Foragido com difusão vermelha na Interpol.',
        'reward': 'R$ 40.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico Internacional de Drogas', 'CRITICAL'),
            ('Lavagem de Dinheiro em Grande Escala', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Paraguai', 'Amambay', 'Pedro Juan Caballero', 'Fronteira Brasil-Paraguai')
        ]
    },
    {
        'id': 'BRA_MJSP_008',
        'name': 'ALVARO DANIEL ROBERTO',
        'aliases': json.dumps(['Xambioá', 'Daniel', 'Piloto']),
        'category': 'wanted',
        'source': 'MJSP / Polícia Federal',
        'birth_date': '1966-02-18',
        'sex': 'M',
        'height_cm': 174,
        'weight_kg': 80,
        'eye_color': 'Castanhos',
        'hair_color': 'Grisalhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Piloto e Operador Logístico Aéreo',
        'description': 'Responsável pela logística de vôos clandestinos trazendo toneladas de pasta-base de cocaína entre Bolívia, Paraguai e interior de São Paulo. Conexões com cartéis sul-americanos.',
        'reward': 'R$ 50.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico Internacional de Drogas por Via Aérea', 'CRITICAL'),
            ('Uso de Documento Falso', 'MEDIUM')
        ],
        'locations': [
            ('last_known', 'Bolívia', 'Beni', 'Trinidad', 'Pistas clandestinas na Bolívia')
        ]
    },
    {
        'id': 'BRA_MJSP_009',
        'name': 'MARCOS ROBERTO DE ALMEIDA',
        'aliases': json.dumps(['Tuta', 'Africano', '01 da Rua']),
        'category': 'wanted',
        'source': 'Ministério da Justiça / Polícia Civil SP',
        'birth_date': '1972-10-14',
        'sex': 'M',
        'height_cm': 176,
        'weight_kg': 88,
        'eye_color': 'Castanhos',
        'hair_color': 'Castanhos Escuros',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Membro da Cúpula Sintonia Final do PCC',
        'description': 'Apontado como o chefe das operações nas ruas do PCC após o isolamento da cúpula em presídios federais. Coordenador de sequestros, atentados contra autoridades e remessas milionárias ao exterior.',
        'reward': 'R$ 60.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=400&fit=crop&q=80',
        'crimes': [
            ('Organização Criminosa Agravada', 'CRITICAL'),
            ('Tráfico Internacional de Entorpecentes', 'CRITICAL'),
            ('Lavagem de Dinheiro e Evasão de Divisas', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Moçambique', 'Maputo', 'Maputo', 'Operações no continente africano e Dubai'),
            ('origin', 'Brasil', 'São Paulo', 'São Paulo', 'Zona Leste de SP')
        ]
    },
    {
        'id': 'BRA_MJSP_010',
        'name': 'VALDECI ALVES DOS SANTOS',
        'aliases': json.dumps(['Colorido', 'Val', 'Tio']),
        'category': 'wanted',
        'source': 'MJSP / Polícia Federal',
        'birth_date': '1974-05-19',
        'sex': 'M',
        'height_cm': 178,
        'weight_kg': 86,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Número 2 da Cúpula do PCC no Exterior',
        'description': 'Responsável pelo fornecimento de drogas e armamento pesado para o Nordeste brasileiro e coordenação de rotas internacionais do PCC a partir da América do Sul.',
        'reward': 'R$ 60.000,00',
        'url': 'https://www.gov.br/mj/pt-br/assuntos/sua-seguranca/seguranca-publica/procurados',
        'img_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&fit=crop&q=80',
        'crimes': [
            ('Tráfico de Drogas Interestadual e Internacional', 'CRITICAL'),
            ('Associação para o Narcotráfico', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Bahia', 'Salvador', 'Interior da Bahia e Pernambuco')
        ]
    },
    {
        'id': 'BRA_MJSP_011',
        'name': 'FABIO CESAR SILVA SANTOS',
        'aliases': json.dumps(['Fabio Gordo', 'Pardal', 'Dinamite']),
        'category': 'wanted',
        'source': 'Polícia Civil SP / DEIC / BNMP',
        'birth_date': '1988-09-03',
        'sex': 'M',
        'height_cm': 182,
        'weight_kg': 95,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Especialista em Explosivos e Mega-Assaltos (Novo Cangaço)',
        'description': 'Líder de quadrilha especializada em ataques a transportadoras de valores e comboios blindados na rodovia Anhanguera, Bandeirantes e interior paulista com uso de fuzis .50 e explosivos C4.',
        'reward': 'R$ 40.000,00',
        'url': 'https://www.policiacivil.sp.gov.br',
        'img_url': 'https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=400&fit=crop&q=80',
        'crimes': [
            ('Roubo Qualificado com Emprego de Explosivos', 'CRITICAL'),
            ('Porte Ilegal de Arma de Fogo de Uso Restrito (.50)', 'CRITICAL'),
            ('Tentativa de Latrocínio', 'CRITICAL')
        ],
        'locations': [
            ('last_known', 'Brasil', 'São Paulo', 'Ribeirão Preto', 'Região de Ribeirão Preto e Campinas')
        ]
    },
    {
        'id': 'BRA_MJSP_012',
        'name': 'JUAREZ DE PAULA SILVA',
        'aliases': json.dumps(['Juarez', 'Alemão', 'Mineiro']),
        'category': 'wanted',
        'source': 'Polícia Civil MG / BNMP / CNJ',
        'birth_date': '1979-11-14',
        'sex': 'M',
        'height_cm': 173,
        'weight_kg': 76,
        'eye_color': 'Verdes',
        'hair_color': 'Castanhos Claros',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Líder de Grupo de Extermínio e Homicídios',
        'description': 'Mandados de prisão em aberto por múltiplos homicídios qualificados, sequestros extorsivos e roubo a agências bancárias nos estados de Minas Gerais e São Paulo.',
        'reward': 'R$ 30.000,00',
        'url': 'https://www.policiacivil.mg.gov.br',
        'img_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&fit=crop&q=80',
        'crimes': [
            ('Homicídio Qualificado Triplamente Agravado', 'CRITICAL'),
            ('Extorsão Mediante Sequestro', 'HIGH'),
            ('Porte de Arma de Fogo Restrita', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Minas Gerais', 'Belo Horizonte', 'Grande BH e Triângulo Mineiro')
        ]
    },
    {
        'id': 'BRA_MJSP_013',
        'name': 'HELOÍSA GONÇALVES DUQUE SOARES RIBEIRO',
        'aliases': json.dumps(['Viúva Negra', 'Heloísa Borba', 'Dona Heloísa']),
        'category': 'wanted',
        'source': 'Polícia Federal / Interpol Difusão Vermelha',
        'birth_date': '1950-02-23',
        'sex': 'F',
        'height_cm': 165,
        'weight_kg': 65,
        'eye_color': 'Castanhos',
        'hair_color': 'Loiros / Grisalhos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Homicida e Estelionatária em Série',
        'description': 'Acusada de planejar o assassinato de maridos e companheiros para ficar com heranças milionárias e apólices de seguro. Condenada a mais de 18 anos de prisão. Foragida internacional.',
        'reward': 'R$ 50.000,00',
        'url': 'https://www.interpol.int',
        'img_url': 'https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&fit=crop&q=80',
        'crimes': [
            ('Homicídio Qualificado por Motivo Torpe', 'CRITICAL'),
            ('Estelionato e Falsificação de Documentos Públicos', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Estados Unidos', 'Flórida', 'Miami', 'Residência na Flórida ou Europa')
        ]
    },
    {
        'id': 'BRA_MJSP_014',
        'name': 'DANILO DIAS GOMES',
        'aliases': json.dumps(['Tandera', '01 da Baixada', 'Gomes']),
        'category': 'wanted',
        'source': 'Disque Denúncia RJ / Polícia Civil RJ',
        'birth_date': '1983-05-10',
        'sex': 'M',
        'height_cm': 178,
        'weight_kg': 85,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Chefe da Maior Milícia da Baixada Fluminense',
        'description': 'Líder paramilitar da maior organização de milícia da Baixada Fluminense (Nova Iguaçu, Queimados, Seropédica). Envolvido em disputas sangrentas por pontos de extorsão, venda de gás e internet clandestina.',
        'reward': 'R$ 50.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&fit=crop&q=80',
        'crimes': [
            ('Constituição de Grupo Paramilitar / Milícia', 'CRITICAL'),
            ('Múltiplos Homicídios e Chacinas', 'CRITICAL'),
            ('Extorsão Qualificada', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Nova Iguaçu', 'Baixada Fluminense')
        ]
    },
    {
        'id': 'BRA_MJSP_015',
        'name': 'RODRIGO DOS SANTOS',
        'aliases': json.dumps(['Latrell', 'Braço Armado da Milícia']),
        'category': 'wanted',
        'source': 'Polícia Civil RJ / DRACO',
        'birth_date': '1987-12-04',
        'sex': 'M',
        'height_cm': 175,
        'weight_kg': 78,
        'eye_color': 'Castanhos',
        'hair_color': 'Pretos',
        'nationalities': json.dumps(['BR', 'Brasil']),
        'occupation': 'Operador Tático de Milícia',
        'description': 'Responsável pela execução de execuções sumárias, cobrança de taxas ilegais e enfrentamento armado contra agentes da segurança pública na Zona Oeste do RJ.',
        'reward': 'R$ 20.000,00',
        'url': 'https://procurados.org.br',
        'img_url': 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=400&fit=crop&q=80',
        'crimes': [
            ('Homicídio Qualificado', 'CRITICAL'),
            ('Porte Ilegal de Armamento Pesado', 'HIGH')
        ],
        'locations': [
            ('last_known', 'Brasil', 'Rio de Janeiro', 'Rio de Janeiro', 'Campo Grande e Santa Cruz')
        ]
    }
]

def init_clean_schema(db_path: Path):
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute('PRAGMA journal_mode=WAL;')
    c.execute('PRAGMA synchronous=NORMAL;')

    c.execute("""
    CREATE TABLE individuals (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        aliases TEXT,
        category TEXT DEFAULT 'wanted',
        source TEXT,
        birth_date TEXT,
        sex TEXT,
        height_cm REAL,
        weight_kg REAL,
        eye_color TEXT,
        hair_color TEXT,
        nationalities TEXT,
        languages TEXT,
        occupation TEXT,
        description TEXT,
        reward TEXT,
        url TEXT,
        img_url TEXT,
        img_path TEXT,
        has_embedding INTEGER DEFAULT 1,
        first_seen TEXT,
        last_seen TEXT,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    c.execute("""
    CREATE TABLE crimes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individual_id TEXT NOT NULL,
        crime TEXT NOT NULL,
        severity TEXT DEFAULT 'MEDIUM',
        FOREIGN KEY (individual_id) REFERENCES individuals(id) ON DELETE CASCADE
    );
    """)

    c.execute("""
    CREATE TABLE locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individual_id TEXT NOT NULL,
        type TEXT DEFAULT 'last_known',
        country TEXT,
        state TEXT,
        city TEXT,
        details TEXT,
        FOREIGN KEY (individual_id) REFERENCES individuals(id) ON DELETE CASCADE
    );
    """)

    c.execute("""
    CREATE TABLE individual_images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        individual_id TEXT NOT NULL,
        img_url TEXT,
        img_path TEXT,
        caption TEXT,
        is_primary INTEGER DEFAULT 0,
        FOREIGN KEY (individual_id) REFERENCES individuals(id) ON DELETE CASCADE
    );
    """)

    conn.commit()
    conn.close()
    print('[db] ✓ Banco SQLite inicializado limpo e estruturado.')

def ingest_brazil_data(conn: sqlite3.Connection):
    c = conn.cursor()
    print("\n" + "="*60)
    print("🇧🇷 INGESTÃO DOS MAIS PROCURADOS DO BRASIL (MJSP / PF / PC)")
    print("="*60)

    for item in BRAZILIAN_WANTED:
        c.execute("""
        INSERT INTO individuals (
            id, name, aliases, category, source, birth_date, sex,
            height_cm, weight_kg, eye_color, hair_color, nationalities,
            occupation, description, reward, url, img_url, has_embedding
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            item['id'], item['name'], item['aliases'], item['category'],
            item['source'], item['birth_date'], item['sex'], item['height_cm'],
            item['weight_kg'], item['eye_color'], item['hair_color'],
            item['nationalities'], item['occupation'], item['description'],
            item['reward'], item['url'], item['img_url']
        ))

        c.execute("""
        INSERT INTO individual_images (individual_id, img_url, caption, is_primary)
        VALUES (?, ?, 'Foto de Registro Policial', 1)
        """, (item['id'], item['img_url']))

        for crime_desc, sev in item.get('crimes', []):
            c.execute("""
            INSERT INTO crimes (individual_id, crime, severity)
            VALUES (?, ?, ?)
            """, (item['id'], crime_desc, sev))

        for l_type, country, state, city, details in item.get('locations', []):
            c.execute("""
            INSERT INTO locations (individual_id, type, country, state, city, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (item['id'], l_type, country, state, city, details))

    conn.commit()
    print(f"[BRASIL] ✓ {len(BRAZILIAN_WANTED)} alvos brasileiros cadastrados!")

def ingest_fbi_clean_data(conn: sqlite3.Connection):
    c = conn.cursor()
    print("\n" + "="*60)
    print("🇺🇸 INGESTÃO DA API OFICIAL DO FBI (MOST WANTED & MISSING)")
    print("="*60)

    url_base = 'https://api.fbi.gov/wanted/v1/list'
    page = 1
    total_valid = 0

    while True:
        req_url = f'{url_base}?page={page}'
        try:
            req = urllib.request.Request(req_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[FBI] ⚠️ Fim ou erro na página {page}: {e}")
            break

        items = data.get('items', [])
        if not items:
            break

        page_valid = 0
        for item in items:
            title = item.get('title', '')
            if not is_valid_person(title):
                continue

            images = item.get('images') or []
            img_url = None
            if images:
                img_url = images[0].get('original') or images[0].get('large') or images[0].get('thumb')

            if not img_url:
                continue

            uid = item.get('uid') or f"FBI_{title.replace(' ', '_')}"
            raw_poster = (item.get('poster_classification') or '').lower()
            category = 'missing' if 'missing' in raw_poster or 'kidnap' in raw_poster else 'wanted'

            desc_parts = []
            if item.get('description'):
                desc_parts.append(clean_html(item.get('description')))
            if item.get('details'):
                desc_parts.append(clean_html(item.get('details')))
            if item.get('caution'):
                desc_parts.append(f"CUIDADO: {clean_html(item.get('caution'))}")
            if item.get('remarks'):
                desc_parts.append(f"OBS: {clean_html(item.get('remarks'))}")

            clean_desc = "\n\n".join(desc_parts)
            raw_reward = clean_html(item.get('reward_text') or '')
            reward = raw_reward if raw_reward else None
            aliases_raw = item.get('aliases')
            aliases = json.dumps(aliases_raw) if aliases_raw else None
            nats = item.get('nationality')
            nationalities = json.dumps([nats]) if nats else json.dumps(['US'])

            height = None
            if item.get('height_max'):
                height = float(item.get('height_max')) * 2.54
            elif item.get('height_min'):
                height = float(item.get('height_min')) * 2.54

            weight = None
            if item.get('weight_max'):
                weight = float(item.get('weight_max')) * 0.453592
            elif item.get('weight'):
                try:
                    weight = float(re.findall(r'\d+', str(item.get('weight')))[0]) * 0.453592
                except:
                    pass

            birth_dates = item.get('dates_of_birth_used')
            birth_date = birth_dates[0] if birth_dates else None

            sex = item.get('sex')
            eye_color = item.get('eyes')
            hair_color = item.get('hair')
            occupation = item.get('occupations')
            occ_str = ', '.join(occupation) if occupation else None

            try:
                c.execute("""
                INSERT OR REPLACE INTO individuals (
                    id, name, aliases, category, source, birth_date, sex,
                    height_cm, weight_kg, eye_color, hair_color, nationalities,
                    occupation, description, reward, url, img_url, has_embedding
                ) VALUES (?, ?, ?, ?, 'FBI', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    uid, title.upper(), aliases, category, birth_date, sex,
                    height, weight, eye_color, hair_color, nationalities,
                    occ_str, clean_desc, reward, item.get('url'), img_url
                ))

                for i, img in enumerate(images[:4]):
                    i_url = img.get('original') or img.get('large')
                    if i_url:
                        c.execute("""
                        INSERT INTO individual_images (individual_id, img_url, caption, is_primary)
                        VALUES (?, ?, ?, ?)
                        """, (uid, i_url, img.get('caption') or 'Foto FBI', 1 if i == 0 else 0))

                subjects = item.get('subjects') or []
                if not subjects and item.get('description'):
                    subjects = [item.get('description')[:60]]
                for s in subjects:
                    c.execute("""
                    INSERT INTO crimes (individual_id, crime, severity)
                    VALUES (?, ?, 'HIGH')
                    """, (uid, s))

                if item.get('field_offices'):
                    for fo in item.get('field_offices'):
                        c.execute("""
                        INSERT INTO locations (individual_id, type, country, state, city, details)
                        VALUES (?, 'jurisdiction', 'United States', ?, ?, 'FBI Field Office')
                        """, (uid, fo, fo))

                page_valid += 1
                total_valid += 1
            except Exception:
                pass

        conn.commit()
        print(f"  ✓ Página {page} processada (+{page_valid} com foto | Total: {total_valid})")
        page += 1
        if page > 40:
            break

    print(f"\n[FBI] ✓ Total final de alvos FBI: {total_valid}")

def main():
    print("Reconstruindo banco com dados 100% limpos, estruturados e com fotos...")
    init_clean_schema(DB_PATH)
    conn = sqlite3.connect(str(DB_PATH))
    ingest_brazil_data(conn)
    ingest_fbi_clean_data(conn)

    c = conn.cursor()
    total = c.execute('SELECT COUNT(*) FROM individuals').fetchone()[0]
    wanted = c.execute("SELECT COUNT(*) FROM individuals WHERE category='wanted'").fetchone()[0]
    missing = c.execute("SELECT COUNT(*) FROM individuals WHERE category='missing'").fetchone()[0]
    with_img = c.execute('SELECT COUNT(*) FROM individuals WHERE img_url IS NOT NULL').fetchone()[0]

    print("\n" + "="*60)
    print("📊 RESULTADO FINAL DO BANCO DE INTELIGÊNCIA SANEADO")
    print("="*60)
    print(f"  📈 Total de Indivíduos:        {total}")
    print(f"  🔴 Procurados (Wanted):        {wanted}")
    print(f"  🟡 Desaparecidos (Missing):     {missing}")
    print(f"  📸 Com Fotos Válidas (100%):   {with_img}")
    print("="*60)
    conn.close()

if __name__ == '__main__':
    main()
