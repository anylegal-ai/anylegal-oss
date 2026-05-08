
"""
This module contains all country keyword mappings and jurisdiction detection logic
that was previously embedded in anylegal_agent.py.
"""

import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

COUNTRY_KEYWORDS = {

    'ITALY': ['italy', 'italian', 'rome', 'milan', 'italian law', 'italia', 'codice civile'],
    'FRANCE': ['france', 'french', 'paris', 'french law', 'français', 'code civil', 'marseille', 'lyon', 'société à responsabilité limitée', 'sarl'],
    'GERMANY': ['germany', 'german', 'berlin', 'german law', 'deutschland', 'münchen', 'hamburg', 'bürgerliches gesetzbuch', 'gmbh', 'gesellschaft mit beschränkter haftung'],
    'SPAIN': ['spain', 'spanish', 'madrid', 'barcelona', 'spanish law', 'españa', 'código civil'],
    'NETHERLANDS': ['netherlands', 'dutch', 'amsterdam', 'holland', 'dutch law', 'nederland', 'burgerlijk wetboek'],
    'BELGIUM': ['belgium', 'belgian', 'brussels', 'belgian law', 'belgique', 'belgë'],
    'SWITZERLAND': ['switzerland', 'swiss', 'zurich', 'geneva', 'bern', 'swiss law'],
    'AUSTRIA': ['austria', 'austrian', 'vienna', 'austrian law', 'österreich'],
    'PORTUGAL': ['portugal', 'portuguese', 'lisbon', 'porto', 'portuguese law'],
    'SWEDEN': ['sweden', 'swedish', 'stockholm', 'swedish law', 'sverige'],
    'NORWAY': ['norway', 'norwegian', 'oslo', 'norwegian law', 'norge'],
    'DENMARK': ['denmark', 'danish', 'copenhagen', 'danish law', 'danmark'],
    'FINLAND': ['finland', 'finnish', 'helsinki', 'finnish law', 'suomi'],
    'POLAND': ['poland', 'polish', 'warsaw', 'krakow', 'polish law', 'polska'],
    'CZECH_REPUBLIC': ['czech republic', 'czech', 'prague', 'czech law', 'česká republika'],
    'HUNGARY': ['hungary', 'hungarian', 'budapest', 'hungarian law', 'magyarország'],
    'GREECE': ['greece', 'greek', 'athens', 'greek law', 'ελλάδα'],
    'IRELAND': ['ireland', 'irish', 'dublin', 'irish law', 'éire'],
    'LUXEMBOURG': ['luxembourg', 'luxembourgish', 'luxembourg law'],
    'ROMANIA': ['romania', 'romanian', 'bucharest', 'romanian law', 'românia'],
    'BULGARIA': ['bulgaria', 'bulgarian', 'sofia', 'bulgarian law', 'българия'],
    'CROATIA': ['croatia', 'croatian', 'zagreb', 'croatian law', 'hrvatska'],
    'SLOVENIA': ['slovenia', 'slovenian', 'ljubljana', 'slovenian law', 'slovenija'],
    'SLOVAKIA': ['slovakia', 'slovak', 'bratislava', 'slovak law', 'slovensko'],
    'ESTONIA': ['estonia', 'estonian', 'tallinn', 'estonian law', 'eesti'],
    'LATVIA': ['latvia', 'latvian', 'riga', 'latvian law', 'latvija'],
    'LITHUANIA': ['lithuania', 'lithuanian', 'vilnius', 'lithuanian law', 'lietuva'],

    'CANADA': ['canada', 'canadian', 'toronto', 'montreal', 'vancouver', 'ontario', 'quebec', 'canadian law'],
    'MEXICO': ['mexico', 'mexican', 'mexico city', 'guadalajara', 'mexican law', 'méxico'],
    'BRAZIL': ['brazil', 'brazilian', 'são paulo', 'rio de janeiro', 'brasília', 'brazilian law', 'brasil'],
    'ARGENTINA': ['argentina', 'argentinian', 'argentine', 'buenos aires', 'córdoba', 'argentinian law'],
    'COLOMBIA': ['colombia', 'colombian', 'bogotá', 'medellín', 'colombian law'],
    'CHILE': ['chile', 'chilean', 'santiago', 'valparaíso', 'chilean law'],
    'PERU': ['peru', 'peruvian', 'lima', 'cusco', 'peruvian law', 'perú'],
    'VENEZUELA': ['venezuela', 'venezuelan', 'caracas', 'venezuelan law'],
    'URUGUAY': ['uruguay', 'uruguayan', 'montevideo', 'uruguayan law'],
    'PARAGUAY': ['paraguay', 'paraguayan', 'asunción', 'paraguayan law'],
    'BOLIVIA': ['bolivia', 'bolivian', 'la paz', 'sucre', 'bolivian law'],
    'ECUADOR': ['ecuador', 'ecuadorian', 'quito', 'guayaquil', 'ecuadorian law'],
    'PANAMA': ['panama', 'panamanian', 'panama city', 'panamanian law', 'panamá'],
    'COSTA_RICA': ['costa rica', 'costa rican', 'san josé', 'costa rican law'],
    'GUATEMALA': ['guatemala', 'guatemalan', 'guatemala city', 'guatemalan law'],
    'HONDURAS': ['honduras', 'honduran', 'tegucigalpa', 'honduran law'],
    'EL_SALVADOR': ['el salvador', 'salvadoran', 'san salvador', 'salvadoran law'],
    'NICARAGUA': ['nicaragua', 'nicaraguan', 'managua', 'nicaraguan law'],
    'DOMINICAN_REPUBLIC': ['dominican republic', 'dominican', 'santo domingo', 'dominican law'],
    'CUBA': ['cuba', 'cuban', 'havana', 'cuban law'],
    'JAMAICA': ['jamaica', 'jamaican', 'kingston', 'jamaican law'],

    'CHINA': ['china', 'chinese', 'beijing', 'shanghai', 'guangzhou', 'chinese law', '中国', '中华人民共和国', 'wfoe'],
    'JAPAN': ['japan', 'japanese', 'tokyo', 'osaka', 'kyoto', 'japanese law', '日本', 'nihon', 'kabushiki kaisha', 'godo kaisha'],
    'SOUTH_KOREA': ['south korea', 'korean', 'seoul', 'busan', 'korean law', '한국', 'korea'],
    'INDIA': ['india', 'indian', 'new delhi', 'mumbai', 'bangalore', 'kolkata', 'indian law', 'भारत'],
    'INDONESIA': ['indonesia', 'indonesian', 'jakarta', 'surabaya', 'indonesian law'],
    'THAILAND': ['thailand', 'thai', 'bangkok', 'thai law', 'ประเทศไทย'],
    'VIETNAM': ['vietnam', 'vietnamese', 'hanoi', 'ho chi minh', 'vietnamese law', 'việt nam'],
    'MALAYSIA': ['malaysia', 'malaysian', 'kuala lumpur', 'malaysian law', 'sdn bhd', 'sdn. bhd.', 'sdn.bhd', 'sdn bhd.', 'sendirian berhad', 'suruhanjaya syarikat malaysia', 'ssm', 'kpkt', 'kementerian perumahan dan kerajaan tempatan', 'ministry of housing and local government', 'moneylenders act 1951', 'bank negara malaysia', 'bnm', 'securities commission malaysia', 'sc malaysia'],
    'SINGAPORE': ['singapore', 'singaporean', 'singapore law', 'pte ltd', 'pte. ltd.', 'pte.ltd', 'pte ltd.', 'private limited', 'acra', 'companies house singapore', 'mas', 'monetary authority of singapore'],
    'PHILIPPINES': ['philippines', 'filipino', 'philippine', 'manila', 'philippine law', 'pilipinas'],
    'TAIWAN': ['taiwan', 'taiwanese', 'taipei', 'taiwanese law', '台灣', '中華民國'],
    'HONG_KONG': ['hong kong', 'hongkong', 'hong kong law', '香港', 'companies registry hong kong', 'cr hong kong'],
    'BANGLADESH': ['bangladesh', 'bangladeshi', 'dhaka', 'chittagong', 'bangladeshi law', 'বাংলাদেশ'],
    'PAKISTAN': ['pakistan', 'pakistani', 'islamabad', 'karachi', 'lahore', 'pakistani law', 'پاکستان'],
    'SRI_LANKA': ['sri lanka', 'sri lankan', 'colombo', 'sri lankan law'],
    'MYANMAR': ['myanmar', 'burmese', 'yangon', 'myanmar law', 'burma'],
    'CAMBODIA': ['cambodia', 'cambodian', 'phnom penh', 'cambodian law'],
    'LAOS': ['laos', 'laotian', 'vientiane', 'laotian law'],
    'MONGOLIA': ['mongolia', 'mongolian', 'ulaanbaatar', 'mongolian law'],
    'NEPAL': ['nepal', 'nepalese', 'kathmandu', 'nepalese law', 'नेपाल'],
    'UZBEKISTAN': ['uzbekistan', 'uzbek', 'tashkent', 'uzbek law', 'oʻzbekiston'],
    'KAZAKHSTAN': ['kazakhstan', 'kazakh', 'nur-sultan', 'almaty', 'kazakh law', 'қазақстан'],
    'KYRGYZSTAN': ['kyrgyzstan', 'kyrgyz', 'bishkek', 'kyrgyz law'],
    'TAJIKISTAN': ['tajikistan', 'tajik', 'dushanbe', 'tajik law'],
    'TURKMENISTAN': ['turkmenistan', 'turkmen', 'ashgabat', 'turkmen law'],
    'AFGHANISTAN': ['afghanistan', 'afghan', 'kabul', 'afghan law', 'افغانستان'],

    'SAUDI_ARABIA': ['saudi arabia', 'saudi', 'riyadh', 'jeddah', 'saudi law', 'السعودية'],
    'TURKEY': ['turkey', 'turkish', 'ankara', 'istanbul', 'turkish law', 'türkiye'],
    'IRAN': ['iran', 'iranian', 'tehran', 'iranian law', 'ایران', 'persia', 'persian'],
    'ISRAEL': ['israel', 'israeli', 'jerusalem', 'tel aviv', 'israeli law', 'ישראל'],
    'JORDAN': ['jordan', 'jordanian', 'amman', 'jordanian law', 'الأردن'],
    'LEBANON': ['lebanon', 'lebanese', 'beirut', 'lebanese law', 'لبنان'],
    'SYRIA': ['syria', 'syrian', 'damascus', 'syrian law', 'سوريا'],
    'IRAQ': ['iraq', 'iraqi', 'baghdad', 'iraqi law', 'العراق'],
    'KUWAIT': ['kuwait', 'kuwaiti', 'kuwait city', 'kuwaiti law', 'الكويت'],
    'QATAR': ['qatar', 'qatari', 'doha', 'qatari law', 'قطر'],
    'BAHRAIN': ['bahrain', 'bahraini', 'manama', 'bahraini law', 'البحرين'],
    'OMAN': ['oman', 'omani', 'muscat', 'omani law', 'عُمان'],
    'YEMEN': ['yemen', 'yemeni', 'sanaa', 'yemeni law', 'اليمن'],
    'CYPRUS': ['cyprus', 'cypriot', 'nicosia', 'cypriot law', 'κύπρος'],
    'GEORGIA': ['georgia', 'georgian', 'tbilisi', 'georgian law', 'საქართველო'],
    'ARMENIA': ['armenia', 'armenian', 'yerevan', 'armenian law', 'հայաստան'],
    'AZERBAIJAN': ['azerbaijan', 'azerbaijani', 'baku', 'azerbaijani law', 'azərbaycan'],

    'SOUTH_AFRICA': ['south africa', 'south african', 'cape town', 'johannesburg', 'pretoria', 'south african law'],
    'EGYPT': ['egypt', 'egyptian', 'cairo', 'alexandria', 'egyptian law', 'مصر'],
    'NIGERIA': ['nigeria', 'nigerian', 'lagos', 'abuja', 'nigerian law'],
    'KENYA': ['kenya', 'kenyan', 'nairobi', 'mombasa', 'kenyan law'],
    'ETHIOPIA': ['ethiopia', 'ethiopian', 'addis ababa', 'ethiopian law'],
    'GHANA': ['ghana', 'ghanaian', 'accra', 'ghanaian law'],
    'UGANDA': ['uganda', 'ugandan', 'kampala', 'ugandan law'],
    'TANZANIA': ['tanzania', 'tanzanian', 'dar es salaam', 'dodoma', 'tanzanian law'],
    'MOZAMBIQUE': ['mozambique', 'mozambican', 'maputo', 'mozambican law', 'moçambique'],
    'MADAGASCAR': ['madagascar', 'malagasy', 'antananarivo', 'malagasy law'],
    'CAMEROON': ['cameroon', 'cameroonian', 'yaoundé', 'douala', 'cameroonian law', 'cameroun'],
    'IVORY_COAST': ['ivory coast', 'ivorian', 'abidjan', 'yamoussoukro', 'ivorian law', 'côte d\'ivoire'],
    'ANGOLA': ['angola', 'angolan', 'luanda', 'angolan law'],
    'MOROCCO': ['morocco', 'moroccan', 'rabat', 'casablanca', 'moroccan law', 'المغرب'],
    'ALGERIA': ['algeria', 'algerian', 'algiers', 'algerian law', 'الجزائر'],
    'TUNISIA': ['tunisia', 'tunisian', 'tunis', 'tunisian law', 'تونس'],
    'LIBYA': ['libya', 'libyan', 'tripoli', 'libyan law', 'ليبيا'],
    'SUDAN': ['sudan', 'sudanese', 'khartoum', 'sudanese law', 'السودان'],
    'ZAMBIA': ['zambia', 'zambian', 'lusaka', 'zambian law'],
    'ZIMBABWE': ['zimbabwe', 'zimbabwean', 'harare', 'zimbabwean law'],
    'BOTSWANA': ['botswana', 'botswanan', 'gaborone', 'botswanan law'],
    'NAMIBIA': ['namibia', 'namibian', 'windhoek', 'namibian law'],
    'SENEGAL': ['senegal', 'senegalese', 'dakar', 'senegalese law', 'sénégal'],
    'MALI': ['mali', 'malian', 'bamako', 'malian law'],
    'BURKINA_FASO': ['burkina faso', 'burkinabé', 'ouagadougou', 'burkinabé law'],
    'NIGER': ['niger', 'nigerien', 'niamey', 'nigerien law'],
    'CHAD': ['chad', 'chadian', 'n\'djamena', 'chadian law', 'tchad'],
    'RWANDA': ['rwanda', 'rwandan', 'kigali', 'rwandan law'],
    'BURUNDI': ['burundi', 'burundian', 'gitega', 'burundian law'],
    'SOMALIA': ['somalia', 'somali', 'mogadishu', 'somali law', 'الصومال'],
    'DJIBOUTI': ['djibouti', 'djiboutian', 'djibouti city', 'djiboutian law'],
    'ERITREA': ['eritrea', 'eritrean', 'asmara', 'eritrean law'],
    'GAMBIA': ['gambia', 'gambian', 'banjul', 'gambian law'],
    'GUINEA': ['guinea', 'guinean', 'conakry', 'guinean law', 'guinée'],
    'SIERRA_LEONE': ['sierra leone', 'sierra leonean', 'freetown', 'sierra leonean law'],
    'LIBERIA': ['liberia', 'liberian', 'monrovia', 'liberian law'],
    'TOGO': ['togo', 'togolese', 'lomé', 'togolese law'],
    'BENIN': ['benin', 'beninese', 'porto-novo', 'beninese law', 'bénin'],
    'MAURITANIA': ['mauritania', 'mauritanian', 'nouakchott', 'mauritanian law', 'موريتانيا'],
    'CAPE_VERDE': ['cape verde', 'cape verdean', 'praia', 'cape verdean law', 'cabo verde'],
    'SAO_TOME_PRINCIPE': ['são tomé and príncipe', 'são toméan', 'são tomé', 'são toméan law'],
    'SEYCHELLES': ['seychelles', 'seychellois', 'victoria', 'seychellois law'],
    'MAURITIUS': ['mauritius', 'mauritian', 'port louis', 'mauritian law'],
    'COMOROS': ['comoros', 'comorian', 'moroni', 'comorian law', 'جزر القمر'],

    'AUSTRALIA': ['australia', 'australian', 'sydney', 'melbourne', 'brisbane', 'perth', 'australian law', 'pty ltd', 'pty. ltd.', 'pty.ltd', 'pty ltd.', 'proprietary limited', 'asic', 'australian securities and investments commission'],
    'NEW_ZEALAND': ['new zealand', 'new zealand law', 'wellington', 'auckland', 'kiwi'],
    'FIJI': ['fiji', 'fijian', 'suva', 'fijian law'],
    'PAPUA_NEW_GUINEA': ['papua new guinea', 'papua new guinean', 'port moresby', 'papua new guinean law'],
    'SOLOMON_ISLANDS': ['solomon islands', 'solomon islander', 'honiara', 'solomon islands law'],
    'VANUATU': ['vanuatu', 'ni-vanuatu', 'port vila', 'vanuatu law'],
    'SAMOA': ['samoa', 'samoan', 'apia', 'samoan law'],
    'TONGA': ['tonga', 'tongan', 'nuku\'alofa', 'tongan law'],
    'PALAU': ['palau', 'palauan', 'ngerulmud', 'palauan law'],
    'MICRONESIA': ['micronesia', 'micronesian', 'palikir', 'micronesian law'],
    'MARSHALL_ISLANDS': ['marshall islands', 'marshallese', 'majuro', 'marshallese law'],
    'KIRIBATI': ['kiribati', 'i-kiribati', 'tarawa', 'kiribati law'],
    'NAURU': ['nauru', 'nauruan', 'yaren', 'nauruan law'],
    'TUVALU': ['tuvalu', 'tuvaluan', 'funafuti', 'tuvaluan law'],

    'RUSSIA': ['russia', 'russian', 'россия', 'россии', 'россий', 'рф', 'moscow', 'москва', 'saint petersburg', 'санкт-петербург', 'russian law', 'российский закон'],
    'UKRAINE': ['ukraine', 'ukrainian', 'kyiv', 'kiev', 'kharkiv', 'ukrainian law', 'україна'],
    'BELARUS': ['belarus', 'belarusian', 'minsk', 'belarusian law', 'беларусь'],
    'MOLDOVA': ['moldova', 'moldovan', 'chișinău', 'moldovan law'],
}

US_STATE_KEYWORDS = {
    'AL': ['alabama', 'al'], 'AK': ['alaska', 'ak'], 'AZ': ['arizona', 'az'],
    'AR': ['arkansas', 'ar'], 'CA': ['california', 'ca'], 'CO': ['colorado', 'co'],
    'CT': ['connecticut', 'ct'], 'DE': ['delaware', 'de'], 'FL': ['florida', 'fl'],
    'GA': ['georgia', 'ga'], 'HI': ['hawaii', 'hi'], 'ID': ['idaho', 'id'],
    'IL': ['illinois', 'il'], 'IN': ['indiana', 'in'], 'IA': ['iowa', 'ia'],
    'KS': ['kansas', 'ks'], 'KY': ['kentucky', 'ky'], 'LA': ['louisiana', 'la'],
    'ME': ['maine', 'me'], 'MD': ['maryland', 'md'], 'MA': ['massachusetts', 'ma'],
    'MI': ['michigan', 'mi'], 'MN': ['minnesota', 'mn'], 'MS': ['mississippi', 'ms'],
    'MO': ['missouri', 'mo'], 'MT': ['montana', 'mt'], 'NE': ['nebraska', 'ne'],
    'NV': ['nevada', 'nv'], 'NH': ['new hampshire', 'nh'], 'NJ': ['new jersey', 'nj'],
    'NM': ['new mexico', 'nm'], 'NY': ['new york', 'ny'], 'NC': ['north carolina', 'nc'],
    'ND': ['north dakota', 'nd'], 'OH': ['ohio', 'oh'], 'OK': ['oklahoma', 'ok'],
    'OR': ['oregon', 'or'], 'PA': ['pennsylvania', 'pa'], 'RI': ['rhode island', 'ri'],
    'SC': ['south carolina', 'sc'], 'SD': ['south dakota', 'sd'], 'TN': ['tennessee', 'tn'],
    'TX': ['texas', 'tx'], 'UT': ['utah', 'ut'], 'VT': ['vermont', 'vt'],
    'VA': ['virginia', 'va'], 'WA': ['washington', 'wa'], 'WV': ['west virginia', 'wv'],
    'WI': ['wisconsin', 'wi'], 'WY': ['wyoming', 'wy']
}

UAE_KEYWORDS = [
    'uae', 'dubai', 'abu dhabi', 'sharjah', 'ajman', 'ras al khaimah', 'fujairah', 'umm al quwain',
    'emirates', 'emirate', 'difc', 'adgm', 'dmcc', 'federal law', 'cabinet resolution',
    'ministry of justice', 'dubai courts', 'federal court', 'emirates id'
]

USA_KEYWORDS = [
    'usa', 'united states', 'america', 'american', 'california', 'new york', 'texas', 'florida',
    'federal court', 'supreme court', 'congress', 'constitution', 'amendment', 'irs', 'sec',
    'delaware', 'nevada', 'llc', 'corporation', 'inc.', 'state law', 'federal law', 'uspto', 'patent and trademark office',
    'us federal', 'nyse', 'nasdaq', 'us immigration', 'americans with disabilities act', 'foreign corrupt practices act'
]

UK_KEYWORDS = [
    'uk', 'united kingdom', 'britain', 'british', 'england', 'scotland', 'wales', 'northern ireland',
    'parliament', 'house of lords', 'house of commons', 'high court', 'crown court',
    'companies house', 'hmrc', 'limited', 'ltd', 'ltd.', 'plc', 'plc.', 'financial conduct authority'
]

def build_country_lookup() -> Dict[str, str]:
    """Build a lookup dictionary for quick country name mapping."""
    country_lookup = {k.lower(): k for k in COUNTRY_KEYWORDS.keys()}                          

    country_lookup.update({
        "uae": "UAE",
        "united arab emirates": "UAE",
        "usa": "USA",
        "united states": "USA",
        "us": "USA",
        "america": "USA",
        "uk": "UK",
        "united kingdom": "UK",
        "britain": "UK",
        "england": "UK",
        "portugal": "PORTUGAL",
        "indonesia": "INDONESIA"
    })

    return country_lookup

def detect_explicit_jurisdiction_in_query(query: str) -> Optional[str]:
    """
    Detect explicit jurisdiction indicators in the current query.
    Returns jurisdiction code if found, None otherwise.
    """
    query_lower = query.lower()

    for code, kw_list in COUNTRY_KEYWORDS.items():

        country_specific_keywords = [k for k in kw_list if k not in ['ltd', 'limited', 'plc', 'inc.', 'corporation', 'llc']]

        entity_terms = ['gmbh', 'sarl', 'kabushiki kaisha', 'godo kaisha', 'wfoe', 'pte ltd', 'sdn bhd']

        if any(k in query_lower for k in country_specific_keywords) or any(term in query_lower for term in entity_terms if term in kw_list):
            logger.debug(f"Found {code} country-specific keywords in query: '{query[:50]}...'")
            return code

    if any(re.search(r'\b' + re.escape(keyword) + r'\b', query_lower) for keyword in UAE_KEYWORDS):
        logger.debug(f"Found UAE keywords in query: '{query[:50]}...'")
        return 'UAE'

    elif any(re.search(r'\b' + re.escape(keyword) + r'\b', query_lower) for keyword in USA_KEYWORDS):
        logger.debug(f"Found USA keywords in query: '{query[:50]}...'")
        return 'USA'

    elif any(re.search(r'\b' + re.escape(keyword) + r'\b', query_lower) for keyword in UK_KEYWORDS):
        logger.debug(f"Found UK keywords in query: '{query[:50]}...'")
        return 'UK'

    return None

def detect_jurisdictions_in_history(conversation_history: List[Dict], max_messages: int = 20) -> set:
    """
    Scan conversation history for jurisdiction indicators.
    Returns a set of detected jurisdiction codes.
    """
    found_jurisdictions = set()

    if not conversation_history:
        return found_jurisdictions

    for msg in reversed(conversation_history[-max_messages:]):

        if msg.get('role') != 'user' or not msg.get('content'):
            continue

        content_lower = msg['content'].lower()

        if any(keyword in content_lower for keyword in UAE_KEYWORDS):
            found_jurisdictions.add('UAE')
            logger.debug(f"Found UAE jurisdiction in history message: '{msg['content'][:50]}...'")

        if any(keyword in content_lower for keyword in USA_KEYWORDS):
            found_jurisdictions.add('USA')
            logger.debug(f"Found USA jurisdiction in history message: '{msg['content'][:50]}...'")

        for code, kw_list in COUNTRY_KEYWORDS.items():
            if any(k in content_lower for k in kw_list):
                found_jurisdictions.add(code)
                logger.debug(f"Found {code} jurisdiction in history message: '{msg['content'][:50]}...'")

        if any(keyword in content_lower for keyword in UK_KEYWORDS):

            specific_jurisdictions = {'SINGAPORE', 'MALAYSIA', 'HONG_KONG'}
            if not any(jurisdiction in found_jurisdictions for jurisdiction in specific_jurisdictions):
                found_jurisdictions.add('UK')
                logger.debug(f"Found UK jurisdiction in history message: '{msg['content'][:50]}...'")
            else:
                logger.debug(f"Skipped UK jurisdiction due to more specific match: {found_jurisdictions & specific_jurisdictions}")

    return found_jurisdictions

def map_waiting_jurisdiction_response(query: str) -> Optional[str]:
    """
    Map a short country name response when waiting for jurisdiction clarification.
    Returns jurisdiction code if mapped, None otherwise.
    """
    candidate = query.strip().lower()

    if not (1 <= len(candidate.split()) <= 3):
        return None

    country_lookup = build_country_lookup()

    if candidate in country_lookup:
        code = country_lookup[candidate]
        logger.info(f"Waiting-for-jurisdiction mode: mapped '{candidate}' → {code}")
        return code
    else:
        logger.warning(f"Country '{candidate}' not found in lookup table")
        return None

def check_waiting_for_jurisdiction(conversation_history: List[Dict]) -> bool:
    """
    Check if the system is waiting for a jurisdiction clarification from the user.
    Returns True if waiting for jurisdiction, False otherwise.
    """
    if not conversation_history:
        return False

    logger.debug(f"Checking for waiting-for-jurisdiction state in {len(conversation_history)} history messages")

    for m in reversed(conversation_history):
        if m.get("role") != "assistant" or not m.get("content"):
            logger.debug(f"Skipping message - role: {m.get('role')}, has_content: {bool(m.get('content'))}")
            continue

        a_text = m["content"].lower()
        logger.debug(f"Checking assistant message: '{a_text[:100]}...'")

        if "which country" in a_text or "which jurisdiction" in a_text or ("specify" in a_text and "jurisdiction" in a_text):
            logger.info(f"Found clarification prompt - setting waiting_for_juris = True")
            return True

        if "legal framework" in a_text or "##" in a_text or "direct answer" in a_text:
            logger.debug("Found normal structured answer - stopping search")
            break

    return False 