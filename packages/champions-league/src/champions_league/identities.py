from standing_prediction.utils import normalize_team


ALIASES = {
    "maccabi tel aviv": "maccabi tel aviv", "maccabi tel aviv fc": "maccabi tel aviv",
    "sport lisboa e benfica": "benfica", "vitoria guimaraes": "guimaraes",
    "kaa gent": "gent", "st gilloise": "union st gilloise",
    "istanbul basaksehir": "istanbul basaksehir", "buyuksehyr": "istanbul basaksehir",
    "pae olympiakos sfp": "olympiakos", "paok saloniki": "paok",
    "rapid wien": "rapid wien", "sk rapid": "rapid wien",
    "molde fk": "molde", "dinamo kiev": "dynamo kyiv",
    "qarabag agdam fk": "qarabag", "qarabag fk": "qarabag",

    "sp lisbon": "sporting cp", "sporting": "sporting cp", "sporting lisbon": "sporting cp",
    "sporting clube portugal": "sporting cp", "sporting portugal": "sporting cp",
    "brugge": "club brugge", "brugge kv": "club brugge", "club brugge kv": "club brugge",
    "sk slavia praha": "slavia praha", "slavia prague": "slavia praha",
    "sk slovan bratislava": "slovan bratislava", "slovan": "slovan bratislava",
    "fk shakhtar donetsk": "shakhtar donetsk", "shakhtar": "shakhtar donetsk",
    "shakhtar donets'k": "shakhtar donetsk", "shakhtar donets k": "shakhtar donetsk",
    "pae aek": "aek athens", "aek": "aek athens", "aek athens": "aek athens",
    "lask linz": "lask", "fk bodo glimt": "bodo glimt", "bodo glimt": "bodo glimt",
    "viking fk": "viking", "fenerbahce sk": "fenerbahce", "galatasaray sk": "galatasaray",
    "feyenoord rotterdam": "feyenoord", "psv eindhoven": "psv",
    "fk sabah": "sabah", "sabah fk": "sabah", "ajax amsterdam": "ajax",
    "sporting braga": "braga", "sporting clube braga": "braga", "sp braga": "braga",
    "benfica lisbon": "benfica", "sl benfica": "benfica", "sl benfica lisbon": "benfica",
    "olympiakos piraeus": "olympiakos", "olympiacos": "olympiakos", "olympiacos piraeus": "olympiakos",
    "rangers": "rangers", "glasgow rangers": "rangers", "celtic glasgow": "celtic",
    "dinamo zagreb": "dinamo zagreb", "gnk dinamo zagreb": "dinamo zagreb",
    # The Odds API's Europa and Conference League names.
    "nec nijmegen": "nijmegen", "twente enschede": "twente", "sk brann": "brann", "sint truiden": "st truiden",
    "copenhagen": "kobenhavn", "kairat": "fk kairat", "omonoia": "omonia nikosia", "fk borac banja luka": "borac banja luka",
    "crvena zvezda": "red star belgrade", "fk crvena zvezda": "red star belgrade",
    "red bull salzburg": "salzburg", "rb salzburg": "salzburg",
    "rb salzburg salzburg": "salzburg", "sturm graz": "sturm graz", "sk sturm graz": "sturm graz",
    "stade brestois 29": "brest", "brest 29": "brest", "lazio roma": "lazio",
    "viktoria plzen": "viktoria plzen", "fk viktoria plzen": "viktoria plzen",
    "ac sparta praha": "sparta praha", "sparta prague": "sparta praha",
    "fk dynamo kyiv": "dynamo kyiv", "dynamo kiev": "dynamo kyiv", "dynamo": "dynamo kyiv",
    "dynamo kyiv": "dynamo kyiv", "fk qarabag": "qarabag", "qarabag agdam": "qarabag",
    "ferencvarosi tc": "ferencvaros", "ferencvaros tc": "ferencvaros", "ferencvarosi": "ferencvaros",
    "az alkmaar": "az", "union saint gilloise": "union st gilloise", "union sg": "union st gilloise",
    "royale union saint gilloise": "union st gilloise", "rsc anderlecht": "anderlecht",
    "besiktas jk": "besiktas", "athletic bilbao": "athletic", "athletic bilbao athletic": "athletic",
    "fk zorya luhansk": "zorya", "polissya zhytomyr": "polissya", "polissya": "polissya",
    "fk teplice": "teplice", "fk jablonec": "jablonec", "fk mlada boleslav": "mlada boleslav",
    "fk pardubice": "pardubice", "1 slovacko": "slovacko", "1fc slovacko": "slovacko",
    "1 fc slovacko": "slovacko", "fastav zlin": "zlin", "tescoma zlin": "zlin",
    "fk dukla praha": "dukla praha", "dynamo ceske budejovice": "ceske budejovice",
    "sk dynamo ceske budejovice": "ceske budejovice", "bohemians praha 1905": "bohemians 1905",
    "hradec kralove": "hradec kralove", "fk hradec kralove": "hradec kralove",
    "sk sigma olomouc": "sigma olomouc", "fk banik ostrava": "banik ostrava",
    "fk zbrojovka brno": "zbrojovka brno", "sk slovan liberec": "slovan liberec",
    "fk slovan liberec": "slovan liberec", "mfk skalica": "skalica",
    "mfk zemplin michalovce": "michalovce", "msk zilina": "zilina",
    "fk zeleziarne podbrezova": "podbrezova", "zeleziarne podbrezova": "podbrezova",
    "kfc komarno": "komarno", "mfk ruzomberok": "ruzomberok",
    "spartak trnava": "spartak trnava", "as trencin": "trencin",
    "dac 1904 dunajska streda": "dunajska streda", "dac dunajska streda": "dunajska streda",
    "mfk dukla banska bystrica": "banska bystrica", "dukla banska bystrica": "banska bystrica",
    "vi on zlate moravce": "zlate moravce", "vi on zlate moravce vrable": "zlate moravce",
    "tatran presov": "presov", "tatran liptovsky mikulas": "liptovsky mikulas",
    # football-data.org names for clubs the football-data.co.uk CSVs spell differently.
    "nec": "nijmegen", "twente 65": "twente", "fortuna sittard": "for sittard", "pec zwolle": "zwolle",
    "sbv excelsior": "excelsior", "telstar 1963": "telstar", "willem ii tilburg": "willem ii",
    "cambuur leeuwarden": "cambuur", "ado den haag": "den haag",
    "vitoria": "guimaraes", "gd estoril praia": "estoril", "estrela da amadora": "estrela", "cs maritimo": "maritimo",
    "heracles almelo": "heracles", "rkc waalwijk": "waalwijk",
    "heart of midlothian": "hearts",
    # ESPN EL/ECL archive spellings; source links in docs/el-ecl-history-evaluation.md.
    "racing genk": "genk", "rapid vienna": "rapid wien", "sint truidense": "st truiden",
}

AREA_LEAGUES = {
    "England": "PL", "Spain": "PD", "Germany": "BL1", "Italy": "SA", "France": "FL1",
    "Portugal": "P1", "Netherlands": "N1", "Belgium": "B1", "Turkey": "T1", "Greece": "G1",
    "Austria": "AUT", "Norway": "NOR", "Czech Republic": "CZ1", "Slovakia": "SK1",
    "Ukraine": "UA1", "Azerbaijan": "AZ1", "Scotland": "SC0", "Switzerland": "CH1",
    "Croatia": "HR1", "Serbia": "RS1", "Hungary": "HU1", "Romania": "RO1", "Poland": "PO1",
    "Denmark": "DK1", "Sweden": "SE1", "Cyprus": "CY1", "Slovenia": "SI1", "Finland": "FI1",
    "Ireland": "IE1", "Northern Ireland": "NI1", "Iceland": "IS1", "Wales": "WA1",
    "Kazakhstan": "KZ1", "Bosnia and Herzegovina": "BA1", "Armenia": "AM1", "Belarus": "BY1",
    "Moldova": "MD1", "Latvia": "LV1", "Lithuania": "LT1", "Estonia": "EE1", "Albania": "AL1",
}
COUNTRY_LEAGUES = dict(zip(
    "ENG ESP GER ITA FRA POR NED BEL TUR GRE AUT NOR CZE SVK UKR AZE SCO SUI CRO SRB HUN ROU POL DEN SWE CYP SVN FIN IRL NIR ISL WAL KAZ BIH ARM BLR MDA LVA LTU EST ALB".split(),
    AREA_LEAGUES.values(),
))


def canonical_team(name):
    name = str(name).translate(str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "Ae", "ł": "l", "Ł": "L", "ð": "d", "đ": "d", "ə": "e", "ı": "i", "ß": "ss"}))
    normalized = normalize_team(name)
    return ALIASES.get(normalized, normalized)
