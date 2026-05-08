"""
Jurisdiction Manager for AnyLegal AI

This module centralizes the configuration for different legal jurisdictions,
allowing the application to dynamically adjust its behavior based on the
user's query.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict

@dataclass
class JurisdictionConfig:
    """Configuration for a single legal jurisdiction."""
    name: str
    code: str
    official_domains: List[str]
    priority_domains: List[str]
    system_prompt_suffix: str
    supported_languages: List[str]
    has_specialized_rag: bool = False
    has_official_search: bool = True
    disclaimer_text: str = ""
    rag_collection: Optional[str] = None
    citation_links_file: Optional[str] = None
    statutory_urls: Dict[str, Dict[str, str]] = field(default_factory=dict)
    known_documents: Dict[str, Dict[str, str]] = field(default_factory=dict)
    enhancement_rules: Dict[str, Dict[str, Dict[str, List[str]]]] = field(default_factory=dict)
    states: Dict[str, Dict[str, Dict[str, List[str]]]] = field(default_factory=dict)
    native_legal_terms: Dict[str, str] = field(default_factory=dict)

JURISDICTION_CONFIGS: Dict[str, JurisdictionConfig] = {
    "UAE": JurisdictionConfig(
        name="United Arab Emirates",
        code="UAE",
        rag_collection="a3ba88e7-a0a9-475d-b0db-5a93966055e8",                         
        official_domains=[
            "uaelegislation.gov.ae", "moj.gov.ae", "u.ae", "federalgazette.gov.ae",
            "abudhabi.gov.ae", "adjd.gov.ae", "dlp.dubai.gov.ae", "dc.gov.ae",
            "sharjah.ae", "ajmanlegal.gov.ae", "rak.ae", "fujairah.gov.ae", "uaq.gov.ae",
            "adgm.com", "kizad.ae", "twofour54.com", "masdarcityfreezone.com",
            "zonescorp.com", "adafz.ae", "creativecity.ae", "jafza.ae", "difc.ae",
            "dmcc.ae", "dafz.ae", "dic.ae", "dmc.ae", "dsoa.ae", "dubaisouth.ae",
            "ifza.com", "dubaiautozone.ae", "dhcc.ae", "dsp.ae", "dubaidesigndistrict.com",
            "dkp.ae", "dubaistudiocity.ae", "dpc.ae", "dubaicommercity.ae",
            "meydanfreezone.com", "texmas.com", "dmca.ae", "diacedu.ae",
            "dubaioutsourcecity.ae", "goldanddiamondpark.com", "ihc.ae", "saif-zone.com",
            "hfza.ae", "shams.ae", "spcfz.com", "srtip.ae", "comtech.ae", "rakez.com",
            "rakmaritimecity.ae", "rakftz.com", "fujairahfreezone.com", "foiz.ae",
            "afz.ae", "amcfz.com", "uaqftz.com"
        ],
        priority_domains=[
            "gov.ae", "difc.ae", "adgm.com", "federalgazette.gov.ae",
            "dubaicourts.gov.ae", "adjd.gov.ae", "rakcourts.gov.ae", "shjc.sharjah.ae"
        ],
        system_prompt_suffix="using authoritative legal sources for the configured jurisdiction",
        citation_links_file="links.txt",
        supported_languages=["en", "ar"],
        has_specialized_rag=True,
        has_official_search=True,
        disclaimer_text=""                                                        
    ),

    "ITALY": JurisdictionConfig(
        name="Italy",
        code="ITALY",
        rag_collection=None,
        official_domains=["gazzettaufficiale.it", "parlamento.it", "camera.it", "senato.it", "cortecostituzionale.it", "cortedicassazione.it", "giustizia.it", "bancaditalia.it", "normattiva.it", "dejure.it", "italgiure.giustizia.it", "corteconti.it", "consigliodistato.it", "csm.it", "agenziaentrate.gov.it", "mit.gov.it", "interno.gov.it", "esteri.it", "salute.gov.it", "mise.gov.it", "mef.gov.it", "miur.gov.it", "lavoro.gov.it", "minambiente.it", "politicheagricole.it", "infrastrutturetrasporti.it", "difesa.it", "governo.it", "quirinale.it"],
        priority_domains=[".gov.it", ".it"],
        system_prompt_suffix="searching current Italian legal sources",
        citation_links_file=None,
        supported_languages=["it", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Italian legal database. For specific legal advice, consult a qualified Italian attorney."
    ),
    "FRANCE": JurisdictionConfig(
        name="France",
        code="FRANCE",
        rag_collection=None,
        official_domains=["legifrance.gouv.fr", "assemblee-nationale.fr", "senat.fr", "conseil-constitutionnel.fr", "courdecassation.fr", "justice.gouv.fr", "banque-france.fr", "dila.premier-ministre.gouv.fr", "conseil-etat.fr", "service-public.fr", "vie-publique.fr", "economie.gouv.fr", "interieur.gouv.fr", "defense.gouv.fr", "diplomatie.gouv.fr", "education.gouv.fr", "travail-emploi.gouv.fr", "ecologie.gouv.fr", "agriculture.gouv.fr", "culture.gouv.fr", "sports.gouv.fr", "solidarites-sante.gouv.fr", "gouvernement.fr", "elysee.fr"],
        priority_domains=[".gouv.fr", ".fr"],
        system_prompt_suffix="searching current French legal sources",
        citation_links_file=None,
        supported_languages=["fr", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized French legal database. For specific legal advice, consult a qualified French attorney."
    ),
    "GERMANY": JurisdictionConfig(
        name="Germany",
        code="GERMANY",
        rag_collection=None,
        official_domains=["recht.bund.de", "bgbl.de", "bundestag.de", "bundesrat.de", "bundesverfassungsgericht.de", "bmjv.de", "bundesgerichtshof.de", "bundesbank.de", "gesetze-im-internet.de", "bundesanzeiger.de", "bmf.de", "bmi.bund.de", "bmwi.de", "bmas.de", "bmg.bund.de", "bmbf.de", "bmfsfj.de", "bmvi.de", "bmub.de", "bmel.de", "bmvg.de", "bundeskanzlerin.de", "bundespraesident.de", "bundesarbeitsgericht.de", "bundesfinanzhof.de", "bundessozialgericht.de", "bundesverwaltungsgericht.de"],
        priority_domains=[".de", ".bund.de"],
        system_prompt_suffix="searching current German legal sources",
        citation_links_file=None,
        supported_languages=["de", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized German legal database. For specific legal advice, consult a qualified German attorney."
    ),
    "SPAIN": JurisdictionConfig(
        name="Spain",
        code="SPAIN",
        rag_collection=None,
        official_domains=["boe.es", "congreso.es", "senado.es", "tribunalconstitucional.es", "poderjudicial.es", "mjusticia.es", "bde.es", "lamoncloa.gob.es", "hacienda.gob.es", "interior.gob.es", "defensa.gob.es", "exteriores.gob.es", "educacion.gob.es", "empleo.gob.es", "miteco.gob.es", "mapa.gob.es", "sanidad.gob.es", "igualdad.gob.es", "cultura.gob.es", "ciencia.gob.es", "transportes.gob.es", "inclusion.gob.es", "casareal.es"],
        priority_domains=[".gob.es", ".es"],
        system_prompt_suffix="searching current Spanish legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Spanish legal database. For specific legal advice, consult a qualified Spanish attorney."
    ),
    "NETHERLANDS": JurisdictionConfig(
        name="Netherlands",
        code="NETHERLANDS",
        rag_collection=None,
        official_domains=["staatsblad.nl", "tweedekamer.nl", "eerstekamer.nl", "rechtspraak.nl", "rijksoverheid.nl", "dnb.nl", "officielebekendmakingen.nl", "zoek.officielebekendmakingen.nl", "wetten.overheid.nl", "overheid.nl", "belastingdienst.nl", "justis.nl", "om.nl", "kadaster.nl", "cbr.nl", "kvk.nl", "rdi.nl", "acm.nl", "afm.nl", "cbpweb.nl", "ser.nl", "raadvanstate.nl", "koninklijkhuis.nl"],
        priority_domains=[".gov.nl", ".nl"],
        system_prompt_suffix="searching current Dutch legal sources",
        citation_links_file=None,
        supported_languages=["nl", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Dutch legal database. For specific legal advice, consult a qualified Dutch attorney."
    ),
    "BELGIUM": JurisdictionConfig(
        name="Belgium",
        code="BELGIUM",
        rag_collection=None,
        official_domains=["moniteur.be", "lachambre.be", "senate.be", "const-court.be", "justice.belgium.be", "nbb.be", "ejustice.just.fgov.be", "belgielex.be", "belgiquelex.be", "belgienlex.be", "jura.be", "strada.be", "codex.vlaanderen.be", "wallex.wallonie.be", "premier.be", "premier.fgov.be", "presscenter.org", "belgium.be", "fgov.be", "finances.belgium.be", "employ.belgium.be", "health.belgium.be", "socialsecurity.belgium.be", "fiscus.fgov.be", "ibz.be", "kruispuntbank.be", "socialsecurity.be"],
        priority_domains=[".be", ".fgov.be"],
        system_prompt_suffix="searching current Belgian legal sources",
        citation_links_file=None,
        supported_languages=["nl", "fr", "de", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Belgian legal database. For specific legal advice, consult a qualified Belgian attorney."
    ),
    "SWITZERLAND": JurisdictionConfig(
        name="Switzerland",
        code="SWITZERLAND",
        rag_collection=None,
        official_domains=["admin.ch", "parlament.ch", "bger.ch", "bj.admin.ch", "snb.ch", "fedlex.admin.ch", "bk.admin.ch", "ch.ch", "efv.admin.ch", "efd.admin.ch", "edi.admin.ch", "uvek.admin.ch", "vbs.admin.ch", "wbf.admin.ch", "ejpd.admin.ch", "eda.admin.ch", "finma.ch", "seco.admin.ch", "bag.admin.ch", "bfs.admin.ch", "meteoschweiz.admin.ch", "are.admin.ch", "bafu.admin.ch"],
        priority_domains=[".admin.ch", ".ch"],
        system_prompt_suffix="searching current Swiss legal sources",
        citation_links_file=None,
        supported_languages=["de", "fr", "it", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Swiss legal database. For specific legal advice, consult a qualified Swiss attorney."
    ),
    "AUSTRIA": JurisdictionConfig(
        name="Austria",
        code="AUSTRIA",
        rag_collection=None,
        official_domains=["ris.bka.gv.at", "parlament.gv.at", "vfgh.gv.at", "justiz.gv.at", "oenb.at", "help.gv.at", "bundeskanzleramt.gv.at", "ogh.gv.at", "vwgh.gv.at", "bmf.gv.at", "bmi.gv.at", "bmeia.gv.at", "bmbwf.gv.at", "bmsgpk.gv.at", "bmk.gv.at", "bmlrt.gv.at", "bmkoes.gv.at", "bmdw.gv.at", "bmafj.gv.at", "bmvit.gv.at", "bundesheer.at", "statistik.at"],
        priority_domains=[".gv.at", ".at"],
        system_prompt_suffix="searching current Austrian legal sources",
        citation_links_file=None,
        supported_languages=["de", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Austrian legal database. For specific legal advice, consult a qualified Austrian attorney."
    ),
    "PORTUGAL": JurisdictionConfig(
        name="Portugal",
        code="PORTUGAL",
        rag_collection=None,
        official_domains=["dre.pt", "parlamento.pt", "pgdlisboa.pt", "tribunalconstitucional.pt", "dgpj.mj.pt", "stj.pt", "tcontas.pt", "igf.min-financas.pt", "presidencia.pt", "portugal.gov.pt", "seg-social.pt", "portaldasfinancas.gov.pt", "bportugal.pt", "cmvm.pt", "anacom.pt", "adene.pt", "asae.gov.pt", "erse.pt", "erc.pt", "cpc.cpc.gov.pt"],
        priority_domains=[".pt", ".gov.pt"],
        system_prompt_suffix="searching current Portuguese legal sources",
        citation_links_file=None,
        supported_languages=["pt", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Portuguese legal database. For specific legal advice, consult a qualified Portuguese attorney."
    ),
    "SWEDEN": JurisdictionConfig(
        name="Sweden",
        code="SWEDEN",
        rag_collection=None,
        official_domains=["riksdag.se", "government.se", "domstol.se", "lagboken.se", "notisum.se", "regeringen.se", "riksbank.se", "skatteverket.se", "bolagsverket.se", "fi.se", "konkurrensverket.se", "konsumentverket.se", "imy.se", "spelinspektionen.se", "socialstyrelsen.se", "folkhalsomyndigheten.se", "arbetsmiljoverket.se", "arbetsformedlingen.se", "pensionsmyndigheten.se", "kronofogden.se"],
        priority_domains=[".se", ".gov.se"],
        system_prompt_suffix="searching current Swedish legal sources",
        citation_links_file=None,
        supported_languages=["sv", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Swedish legal database. For specific legal advice, consult a qualified Swedish attorney."
    ),
    "NORWAY": JurisdictionConfig(
        name="Norway",
        code="NORWAY",
        rag_collection=None,
        official_domains=["regjeringen.no", "stortinget.no", "domstol.no", "lovdata.no", "justisdepartementet.no", "norges-bank.no", "skatteetaten.no", "brreg.no", "finanstilsynet.no", "konkurransetilsynet.no", "forbrukerradet.no", "datatilsynet.no", "lottstift.no", "nav.no", "arbeidstilsynet.no", "toll.no", "kartverket.no", "dirmin.no", "ssb.no", "difi.no"],
        priority_domains=[".no", ".gov.no"],
        system_prompt_suffix="searching current Norwegian legal sources",
        citation_links_file=None,
        supported_languages=["no", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Norwegian legal database. For specific legal advice, consult a qualified Norwegian attorney."
    ),
    "DENMARK": JurisdictionConfig(
        name="Denmark",
        code="DENMARK",
        rag_collection=None,
        official_domains=["retsinformation.dk", "ft.dk", "domstol.dk", "justitsministeriet.dk", "hoejesteret.dk", "nationalbanken.dk", "skat.dk", "cvr.dk", "dfsa.dk", "kfst.dk", "forbrugerombudsmanden.dk", "datatilsynet.dk", "spillemyndigheden.dk", "borger.dk", "virk.dk", "erst.dk", "energitilsynet.dk", "trafikstyrelsen.dk", "sikkerhedsstyrelsen.dk"],
        priority_domains=[".dk", ".gov.dk"],
        system_prompt_suffix="searching current Danish legal sources",
        citation_links_file=None,
        supported_languages=["da", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Danish legal database. For specific legal advice, consult a qualified Danish attorney."
    ),
    "FINLAND": JurisdictionConfig(
        name="Finland",
        code="FINLAND",
        rag_collection=None,
        official_domains=["finlex.fi", "eduskunta.fi", "oikeus.fi", "om.fi", "korkeinoikeus.fi", "bof.fi", "vero.fi", "prh.fi", "finanssivalvonta.fi", "kkv.fi", "kuluttajaliitto.fi", "tietosuoja.fi", "veikkaus.fi", "kela.fi", "tyosuojelu.fi", "tulli.fi", "maanmittauslaitos.fi", "stat.fi", "vm.fi"],
        priority_domains=[".fi", ".gov.fi"],
        system_prompt_suffix="searching current Finnish legal sources",
        citation_links_file=None,
        supported_languages=["fi", "sv", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Finnish legal database. For specific legal advice, consult a qualified Finnish attorney."
    ),
    "POLAND": JurisdictionConfig(
        name="Poland",
        code="POLAND",
        rag_collection=None,
        official_domains=["isap.sejm.gov.pl", "sejm.gov.pl", "senat.gov.pl", "ms.gov.pl", "sn.pl", "nsa.gov.pl", "trybunal.gov.pl", "nik.gov.pl", "nbp.pl", "knf.gov.pl", "uokik.gov.pl", "giodo.gov.pl", "krs.ms.gov.pl", "ceidg.gov.pl", "podatki.gov.pl", "zus.pl", "gus.gov.pl", "prezydent.pl", "kprm.gov.pl"],
        priority_domains=[".gov.pl", ".pl"],
        system_prompt_suffix="searching current Polish legal sources",
        citation_links_file=None,
        supported_languages=["pl", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Polish legal database. For specific legal advice, consult a qualified Polish attorney."
    ),
    "CZECH_REPUBLIC": JurisdictionConfig(
        name="Czech Republic",
        code="CZECH_REPUBLIC",
        rag_collection=None,
        official_domains=["zakonyprolidi.cz", "psp.cz", "senat.cz", "justice.cz", "nsoud.cz", "usoud.cz", "nku.cz", "cnb.cz", "cnb.cz", "uohs.cz", "uoou.cz", "justice.cz", "or.justice.cz", "financnisprava.cz", "cssz.cz", "czso.cz", "hrad.cz", "vlada.cz"],
        priority_domains=[".cz", ".gov.cz"],
        system_prompt_suffix="searching current Czech legal sources",
        citation_links_file=None,
        supported_languages=["cs", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Czech legal database. For specific legal advice, consult a qualified Czech attorney."
    ),
    "HUNGARY": JurisdictionConfig(
        name="Hungary",
        code="HUNGARY",
        rag_collection=None,
        official_domains=["magyarkozlony.hu", "parlament.hu", "birosag.hu", "im.gov.hu", "kuria-birosag.hu", "alkotmanybirosag.hu", "asz.hu", "mnb.hu", "gvh.hu", "naih.hu", "kozlonyok.hu", "e-cegjegyzek.hu", "nav.gov.hu", "nyp.hu", "ksh.hu", "koztarsasag.hu", "kormany.hu"],
        priority_domains=[".hu", ".gov.hu"],
        system_prompt_suffix="searching current Hungarian legal sources",
        citation_links_file=None,
        supported_languages=["hu", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Hungarian legal database. For specific legal advice, consult a qualified Hungarian attorney."
    ),
    "GREECE": JurisdictionConfig(
        name="Greece",
        code="GREECE",
        rag_collection=None,
        official_domains=["et.gr", "hellenicparliament.gr", "ministryofjustice.gr", "areiopagos.gr", "ste.gr", "constitutionalcourt.gr", "elsyn.gr", "bankofgreece.gr", "eett.gr", "dpa.gr", "gsis.gr", "taxisnet.gr", "ika.gr", "statistics.gr", "presidency.gr", "ypes.gr"],
        priority_domains=[".gr", ".gov.gr"],
        system_prompt_suffix="searching current Greek legal sources",
        citation_links_file=None,
        supported_languages=["el", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Greek legal database. For specific legal advice, consult a qualified Greek attorney."
    ),
    "IRELAND": JurisdictionConfig(
        name="Ireland",
        code="IRELAND",
        rag_collection=None,
        official_domains=["irishstatutebook.ie", "oireachtas.ie", "courts.ie", "justice.ie", "supremecourt.ie", "centralbank.ie", "ccpc.ie", "dataprotection.ie", "cro.ie", "revenue.ie", "welfare.ie", "cso.ie", "president.ie", "gov.ie"],
        priority_domains=[".ie", ".gov.ie"],
        system_prompt_suffix="searching current Irish legal sources",
        citation_links_file=None,
        supported_languages=["en", "ga"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Irish legal database. For specific legal advice, consult a qualified Irish solicitor or barrister."
    ),
    "LUXEMBOURG": JurisdictionConfig(
        name="Luxembourg",
        code="LUXEMBOURG",
        rag_collection=None,
        official_domains=["legilux.public.lu", "chd.lu", "conseil-etat.public.lu", "justice.public.lu", "csl.lu", "bcl.lu", "cssf.lu", "cnpd.public.lu", "rcs.lu", "acd.public.lu", "igss.lu", "statec.public.lu", "monarchie.lu", "gouvernement.lu"],
        priority_domains=[".public.lu", ".lu"],
        system_prompt_suffix="searching current Luxembourg legal sources",
        citation_links_file=None,
        supported_languages=["fr", "de", "lb", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Luxembourg legal database. For specific legal advice, consult a qualified Luxembourg attorney."
    ),
    "ROMANIA": JurisdictionConfig(
        name="Romania",
        code="ROMANIA",
        rag_collection=None,
        official_domains=["cdep.ro", "senat.ro", "ccr.ro", "scj.ro", "bnr.ro", "asf.ro", "cnsc.ro", "onrc.ro", "anaf.ro", "mmps.ro", "insse.ro", "presidency.ro", "gov.ro"],
        priority_domains=[".gov.ro", ".ro"],
        system_prompt_suffix="searching current Romanian legal sources",
        citation_links_file=None,
        supported_languages=["ro", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Romanian legal database. For specific legal advice, consult a qualified Romanian attorney."
    ),
    "BULGARIA": JurisdictionConfig(
        name="Bulgaria",
        code="BULGARIA",
        rag_collection=None,
        official_domains=["parliament.bg", "constcourt.bg", "vss.justice.bg", "bnb.bg", "fsc.bg", "cpc.bg", "brra.bg", "nap.bg", "noi.bg", "nsi.bg", "president.bg", "government.bg"],
        priority_domains=[".gov.bg", ".bg"],
        system_prompt_suffix="searching current Bulgarian legal sources",
        citation_links_file=None,
        supported_languages=["bg", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Bulgarian legal database. For specific legal advice, consult a qualified Bulgarian attorney."
    ),
    "CROATIA": JurisdictionConfig(
        name="Croatia",
        code="CROATIA",
        rag_collection=None,
        official_domains=["nn.hr", "sabor.hr", "usud.hr", "vsrh.hr", "hnb.hr", "hanfa.hr", "aztn.hr", "fina.hr", "porezna-uprava.hr", "mirovinsko.hr", "dzs.hr", "predsjednik.hr", "vlada.hr"],
        priority_domains=[".gov.hr", ".hr"],
        system_prompt_suffix="searching current Croatian legal sources",
        citation_links_file=None,
        supported_languages=["hr", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Croatian legal database. For specific legal advice, consult a qualified Croatian attorney."
    ),
    "SLOVENIA": JurisdictionConfig(
        name="Slovenia",
        code="SLOVENIA",
        rag_collection=None,
        official_domains=["pisrs.si", "dz-rs.si", "us-rs.si", "sodisce.si", "bsi.si", "a-tvp.si", "kpk-rs.si", "ajpes.si", "fu.gov.si", "zpiz.si", "stat.si", "up-rs.si", "gov.si"],
        priority_domains=[".gov.si", ".si"],
        system_prompt_suffix="searching current Slovenian legal sources",
        citation_links_file=None,
        supported_languages=["sl", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Slovenian legal database. For specific legal advice, consult a qualified Slovenian attorney."
    ),
    "SLOVAKIA": JurisdictionConfig(
        name="Slovakia",
        code="SLOVAKIA",
        rag_collection=None,
        official_domains=["nrsr.sk", "ustavnysud.sk", "nsn.sk", "nbs.sk", "nbu.gov.sk", "antimon.gov.sk", "orsr.sk", "financnasprava.sk", "socpoist.sk", "statistics.sk", "prezident.sk", "vlada.gov.sk"],
        priority_domains=[".gov.sk", ".sk"],
        system_prompt_suffix="searching current Slovak legal sources",
        citation_links_file=None,
        supported_languages=["sk", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Slovak legal database. For specific legal advice, consult a qualified Slovak attorney."
    ),
    "ESTONIA": JurisdictionConfig(
        name="Estonia",
        code="ESTONIA",
        rag_collection=None,
        official_domains=["riigiteataja.ee", "riigikogu.ee", "riigikohus.ee", "kohus.ee", "eestipank.ee", "fi.ee", "konkurentsiamet.ee", "rik.ee", "emta.ee", "sotsiaalkindlustusamet.ee", "stat.ee", "president.ee", "valitsus.ee"],
        priority_domains=[".gov.ee", ".ee"],
        system_prompt_suffix="searching current Estonian legal sources",
        citation_links_file=None,
        supported_languages=["et", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Estonian legal database. For specific legal advice, consult a qualified Estonian attorney."
    ),
    "LATVIA": JurisdictionConfig(
        name="Latvia",
        code="LATVIA",
        rag_collection=None,
        official_domains=["likumi.lv", "saeima.lv", "satv.tiesa.gov.lv", "at.gov.lv", "bank.lv", "fktk.lv", "kp.gov.lv", "ur.gov.lv", "vid.gov.lv", "vsaa.gov.lv", "csb.gov.lv", "president.lv", "mk.gov.lv"],
        priority_domains=[".gov.lv", ".lv"],
        system_prompt_suffix="searching current Latvian legal sources",
        citation_links_file=None,
        supported_languages=["lv", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Latvian legal database. For specific legal advice, consult a qualified Latvian attorney."
    ),
    "LITHUANIA": JurisdictionConfig(
        name="Lithuania",
        code="LITHUANIA",
        rag_collection=None,
        official_domains=["e-tar.lt", "lrs.lt", "lrkt.lt", "teismai.lt", "lb.lt", "lb.lt", "kt.gov.lt", "registrucentras.lt", "vmi.lt", "sodra.lt", "osp.stat.gov.lt", "president.lt", "lrv.lt"],
        priority_domains=[".gov.lt", ".lt"],
        system_prompt_suffix="searching current Lithuanian legal sources",
        citation_links_file=None,
        supported_languages=["lt", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Lithuanian legal database. For specific legal advice, consult a qualified Lithuanian attorney."
    ),

    "USA": JurisdictionConfig(
        name="United States",
        code="USA",
        rag_collection=None,
        official_domains=[

            "govinfo.gov", "federalregister.gov", "congress.gov", "house.gov", "senate.gov", 
            "supremecourt.gov", "justice.gov", "federalreserve.gov", "uscode.house.gov", 
            "uscourts.gov", "whitehouse.gov", "treasury.gov", "sec.gov", "cftc.gov", 
            "ftc.gov", "cfpb.gov", "fdic.gov", "occ.gov",

            "acus.gov", "archives.gov", "gpo.gov", "gao.gov", "loc.gov", "ecfr.gov", 
            "regulations.gov", "omb.gov", "opm.gov", "dol.gov", "hhs.gov", "ed.gov", 
            "usda.gov", "commerce.gov", "energy.gov", "doi.gov", "state.gov", "defense.gov", 
            "va.gov", "dhs.gov", "hud.gov", "dot.gov", "epa.gov", "fcc.gov", "nlrb.gov", 
            "eeoc.gov", "cpsc.gov", "nrc.gov", "fda.gov", "cdc.gov", "irs.gov", "sba.gov", 
            "pbgc.gov", "ncua.gov", "mspb.gov", "flra.gov", "usitc.gov", "ferc.gov", 
            "fhfa.gov", "fmc.gov", "fra.gov", "faa.gov", "uscis.gov", "ice.gov", "cbp.gov", 
            "tsa.gov", "usss.gov", "fbi.gov", "dea.gov", "atf.gov", "usms.gov", "bop.gov", 
            "fincen.gov", "ttb.gov", "census.gov", "bls.gov", "bea.gov", "usgs.gov", 
            "noaa.gov", "nist.gov", "uspto.gov", "trade.gov", "bis.gov", "export.gov", 
            "usps.gov", "peacecorps.gov", "rrb.gov", "usab.gov", "cppb.gov", "ntsb.gov", 
            "finra.org", "sipc.org", "ofheo.gov", "ots.treas.gov",

            "legislature.state.al.us", "akleg.gov", "azleg.gov", "arkleg.state.ar.us", 
            "assembly.ca.gov", "sen.ca.gov", "sos.ca.gov", "leginfo.legislature.ca.gov", "ca.gov",
            "leg.colorado.gov", "cga.ct.gov", "legis.delaware.gov", "myfloridahouse.gov", 
            "flsenate.gov", "legis.ga.gov", "capitol.hawaii.gov", "legislature.idaho.gov", 
            "ilga.gov", "iga.in.gov", "legis.iowa.gov", "kslegislature.gov", "legislature.ky.gov", 
            "legis.la.gov", "legislature.maine.gov", "mgaleg.maryland.gov", "malegislature.gov", 
            "legislature.mi.gov", "leg.state.mn.us", "legislature.ms.gov", "house.mo.gov", 
            "senate.mo.gov", "leg.mt.gov", "nebraskalegislature.gov", "leg.state.nv.us", 
            "gencourt.state.nh.us", "njleg.state.nj.us", "nmlegis.gov", "assembly.state.ny.us", 
            "nysenate.gov", "ncleg.gov", "ndlegis.gov", "legislature.ohio.gov", "okhouse.gov", 
            "oksenate.gov", "oregonlegislature.gov", "legis.state.pa.us", "rilin.state.ri.us", 
            "scstatehouse.gov", "sdlegislature.gov", "capitol.tn.gov", "capitol.texas.gov", 
            "le.utah.gov", "legislature.vermont.gov", "lis.virginia.gov", "leg.wa.gov", 
            "wvlegislature.gov", "legis.wisconsin.gov", "wyoleg.gov",

            "senadopr.us", "camaraderepresentantes.org", "senado.pr.gov", "legvi.org", 
            "guamlegislature.com", "cnmileg.gov.mp", "asbar.org",

            "fjc.gov", "ussc.gov", "cafc.uscourts.gov", "ca1.uscourts.gov", "ca2.uscourts.gov", 
            "ca3.uscourts.gov", "ca4.uscourts.gov", "ca5.uscourts.gov", "ca6.uscourts.gov", 
            "ca7.uscourts.gov", "ca8.uscourts.gov", "ca9.uscourts.gov", "ca10.uscourts.gov", 
            "ca11.uscourts.gov", "cadc.uscourts.gov", "pacer.gov", "courtlistener.com",

            "law.cornell.edu", "scholar.google.com", "justia.com", "findlaw.com", 
            "law.justia.com", "caselaw.findlaw.com", "casetext.com", "openjurist.org", 
            "leagle.com", "law.resource.org", "lp.findlaw.com", "law.georgetown.edu", 
            "lawhelp.org",

            "americanbar.org", "abanet.org", "uniform-bar-exam.org", "lawschooladmission.org", 
            "lawsoc.org", "ncsc.org", "ncsconline.org", "courtstatistics.org"
        ],
        priority_domains=[".gov", "law.cornell.edu"],
        system_prompt_suffix="searching current US legal sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized US legal database. For specific legal advice, consult a qualified US attorney.",
        statutory_urls={
            "california": {
                "corporations_code": "https://leginfo.legislature.ca.gov/faces/codesTOCSelected.xhtml?tocCode=CORP",
                "llc_act": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=17701.01.&lawCode=CORP"
            },
            "delaware": {
                "general_corporation_law": "https://delcode.delaware.gov/title8/index.shtml",
                "llc_act": "https://delcode.delaware.gov/title6/c018/index.shtml"
            },
            "new_york": {
                "business_corporation_law": "https://www.nysenate.gov/legislation/laws/BSN",
                "llc_law": "https://www.nysenate.gov/legislation/laws/LLC"
            }
        },
        known_documents={

            "delaware_general_corporation_law": {
                "url": "https://delcode.delaware.gov/title8/index.shtml",
                "title": "Delaware General Corporation Law",
                "priority": "high"
            },
            "delaware_llc_act": {
                "url": "https://delcode.delaware.gov/title6/c018/index.shtml",
                "title": "Delaware Limited Liability Company Act"
            },

            "california_corporations_code": {
                 "url": "https://leginfo.legislature.ca.gov/faces/codesTOCSelected.xhtml?tocCode=CORP",
                 "title": "California Corporations Code"
            },
            "california_llc_act": {
                "url": "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?sectionNum=17701.01.&lawCode=CORP",
                "title": "California Revised Uniform Limited Liability Company Act",
            },

            "new_york_business_corporation_law": {
                "url": "https://www.nysenate.gov/legislation/laws/BSN",
                "title": "New York Business Corporation Law"
            },

            "texas_business_organizations_code": {
                "url": "https://statutes.capitol.texas.gov/Docs/BO/htm/BO.1.htm",
                "title": "Texas Business Organizations Code"
            }
        },
        enhancement_rules={
            "california": {
                "llc_queries": ["'operating agreement'", "'section 17701'", "'california corporations code'"],
                "corp_queries": ["'articles of incorporation'", "'section 200'", "'board resolution'"]
            },
            "delaware": {
                "llc_queries": ["'operating agreement'", "'section 18-'", "'delaware llc act'"],
                "corp_queries": ["'certificate of incorporation'", "'section 141'", "'delaware general corporation law'"]
            },
            "new_york": {
                "llc_queries": ["'operating agreement'", "'article 8'", "'new york llc law'"],
                "corp_queries": ["'certificate of incorporation'", "'section 701'", "'business corporation law'"]
            }
        },
        states={
            "california": {
                "official_domains": [
                    "leginfo.legislature.ca.gov",                                
                    "sos.ca.gov",                                                            
                    "courts.ca.gov",                               
                    "dcba.ca.gov",                                                     
                    "www.ca.gov"                                        
                ],
                "priority_domains": [
                    "leginfo.legislature.ca.gov",
                    "sos.ca.gov"
                ],
                "enhancement_rules": {
                    "benefit_corp_queries": ["Corporate Flexibility Act of 2011", "AB 361"]
                }
            }
        }
    ),
    "CANADA": JurisdictionConfig(
        name="Canada",
        code="CANADA",
        rag_collection=None,
        official_domains=["gazette.gc.ca", "parl.ca", "scc-csc.ca", "fct-cf.gc.ca", "justice.gc.ca", "bankofcanada.ca", "laws-lois.justice.gc.ca", "canlii.org", "assembly.ab.ca", "leg.bc.ca", "gov.mb.ca", "gnb.ca", "assembly.nl.ca", "assembly.gov.nt.ca", "nslegislature.ca", "assembly.nu.ca", "ola.org", "assembly.pe.ca", "assnat.qc.ca", "legassembly.sk.ca", "yukonassembly.ca", "canada.ca", "cra-arc.gc.ca", "osfi-bsif.gc.ca", "iiroc.ca", "csc-scc.gc.ca", "ic.gc.ca", "tc.gc.ca", "hc-sc.gc.ca", "esdc.gc.ca", "nrcan.gc.ca", "dfo-mpo.gc.ca", "cbsa-asfc.gc.ca", "gg.ca"],
        priority_domains=[".gc.ca", ".ca"],
        system_prompt_suffix="searching current Canadian legal sources",
        citation_links_file=None,
        supported_languages=["en", "fr"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Canadian legal database. For specific legal advice, consult a qualified Canadian attorney."
    ),
    "MEXICO": JurisdictionConfig(
        name="Mexico",
        code="MEXICO",
        rag_collection=None,
        official_domains=["dof.gob.mx", "senado.gob.mx", "diputados.gob.mx", "scjn.gob.mx", "cjf.gob.mx", "banxico.org.mx", "ordenjuridico.gob.mx", "presidencia.gob.mx", "gob.mx", "shcp.gob.mx", "segob.gob.mx", "sedena.gob.mx", "sre.gob.mx", "sep.gob.mx", "stps.gob.mx", "semarnat.gob.mx", "sagarpa.gob.mx", "salud.gob.mx", "sedesol.gob.mx", "se.gob.mx", "sct.gob.mx", "sectur.gob.mx", "cnbv.gob.mx", "condusef.gob.mx", "sat.gob.mx", "imss.gob.mx", "inegi.org.mx"],
        priority_domains=[".gob.mx", ".mx"],
        system_prompt_suffix="searching current Mexican legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Mexican legal database. For specific legal advice, consult a qualified Mexican attorney."
    ),
    "BRAZIL": JurisdictionConfig(
        name="Brazil",
        code="BRAZIL",
        rag_collection=None,
        official_domains=["in.gov.br", "camara.leg.br", "senado.leg.br", "stf.jus.br", "stj.jus.br", "justica.gov.br", "bcb.gov.br", "planalto.gov.br", "tse.jus.br", "tcu.gov.br", "cvm.gov.br", "susep.gov.br", "fazenda.gov.br", "receita.fazenda.gov.br", "previdencia.gov.br", "ibge.gov.br", "cade.gov.br", "anatel.gov.br", "anp.gov.br", "ancine.gov.br", "antaq.gov.br", "antt.gov.br", "anac.gov.br", "ans.gov.br"],
        priority_domains=[".gov.br", ".leg.br", ".jus.br"],
        system_prompt_suffix="searching current Brazilian legal sources",
        citation_links_file=None,
        supported_languages=["pt", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Brazilian legal database. For specific legal advice, consult a qualified Brazilian attorney."
    ),
    "ARGENTINA": JurisdictionConfig(
        name="Argentina",
        code="ARGENTINA",
        rag_collection=None,
        official_domains=["argentina.gob.ar", "hcdn.gob.ar", "senado.gob.ar", "csjn.gov.ar", "infoleg.gob.ar", "bcra.gob.ar", "cnv.gov.ar", "afip.gob.ar", "anses.gob.ar", "indec.gob.ar", "cndc.gob.ar", "enacom.gob.ar", "casarosada.gob.ar", "jefatura.gob.ar", "economia.gob.ar", "interior.gob.ar", "defensa.gob.ar", "cancilleria.gob.ar", "educacion.gob.ar", "trabajo.gob.ar", "ambiente.gob.ar", "agroindustria.gob.ar", "salud.gob.ar", "desarrollosocial.gob.ar"],
        priority_domains=[".gob.ar", ".gov.ar"],
        system_prompt_suffix="searching current Argentine legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Argentine legal database. For specific legal advice, consult a qualified Argentine attorney."
    ),
    "COLOMBIA": JurisdictionConfig(
        name="Colombia",
        code="COLOMBIA",
        rag_collection=None,
        official_domains=["presidencia.gov.co", "camara.gov.co", "senado.gov.co", "corteconstitucional.gov.co", "cortesuprema.gov.co", "banrep.gov.co", "superfinanciera.gov.co", "dian.gov.co", "colpensiones.gov.co", "dane.gov.co", "sic.gov.co", "crcom.gov.co", "minhacienda.gov.co", "mininterior.gov.co", "mindefensa.gov.co", "cancilleria.gov.co", "mineducacion.gov.co", "mintrabajo.gov.co", "minambiente.gov.co", "minagricultura.gov.co", "minsalud.gov.co", "prosperidadsocial.gov.co"],
        priority_domains=[".gov.co", ".co"],
        system_prompt_suffix="searching current Colombian legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Colombian legal database. For specific legal advice, consult a qualified Colombian attorney."
    ),
    "CHILE": JurisdictionConfig(
        name="Chile",
        code="CHILE",
        rag_collection=None,
        official_domains=["presidencia.gob.cl", "camara.cl", "senado.cl", "tribunalconstitucional.cl", "pjud.cl", "bcentral.cl", "svs.cl", "sii.cl", "ips.gob.cl", "ine.cl", "fne.gob.cl", "subtel.gob.cl", "hacienda.gob.cl", "interior.gob.cl", "defensa.gob.cl", "minrel.gob.cl", "mineduc.cl", "mintrab.gob.cl", "mma.gob.cl", "minagri.gob.cl", "minsal.cl", "desarrollosocial.gob.cl"],
        priority_domains=[".gob.cl", ".cl"],
        system_prompt_suffix="searching current Chilean legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Chilean legal database. For specific legal advice, consult a qualified Chilean attorney."
    ),
    "PERU": JurisdictionConfig(
        name="Peru",
        code="PERU",
        rag_collection=None,
        official_domains=["presidencia.gob.pe", "congreso.gob.pe", "tc.gob.pe", "pj.gob.pe", "minjus.gob.pe", "bcrp.gob.pe", "smv.gob.pe", "sunat.gob.pe", "onp.gob.pe", "inei.gob.pe", "indecopi.gob.pe", "mtc.gob.pe", "mef.gob.pe", "mininter.gob.pe", "mindef.gob.pe", "rree.gob.pe", "minedu.gob.pe", "trabajo.gob.pe", "minam.gob.pe", "minagri.gob.pe", "minsa.gob.pe", "midis.gob.pe"],
        priority_domains=[".gob.pe", ".pe"],
        system_prompt_suffix="searching current Peruvian legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Peruvian legal database. For specific legal advice, consult a qualified Peruvian attorney."
    ),
    "VENEZUELA": JurisdictionConfig(
        name="Venezuela",
        code="VENEZUELA",
        rag_collection=None,
        official_domains=["presidencia.gob.ve", "asambleanacional.gob.ve", "tsj.gob.ve", "bcv.org.ve", "sudeban.gob.ve", "seniat.gob.ve", "ivss.gob.ve", "ine.gob.ve", "cne.gob.ve", "vicepresidencia.gob.ve", "mppeuct.gob.ve", "mininterior.gob.ve", "mindefensa.gob.ve", "mppre.gob.ve", "mppe.gob.ve", "minpptrass.gob.ve", "minamb.gob.ve", "minppagricultura.gob.ve", "mpps.gob.ve"],
        priority_domains=[".gob.ve", ".ve"],
        system_prompt_suffix="searching current Venezuelan legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Venezuelan legal database. For specific legal advice, consult a qualified Venezuelan attorney."
    ),
    "URUGUAY": JurisdictionConfig(
        name="Uruguay",
        code="URUGUAY",
        rag_collection=None,
        official_domains=["presidencia.gub.uy", "parlamento.gub.uy", "poderjudicial.gub.uy", "bcu.gub.uy", "bse.com.uy", "dgi.gub.uy", "bps.gub.uy", "ine.gub.uy", "corteelectoral.gub.uy", "gub.uy", "mef.gub.uy", "minterior.gub.uy", "mdn.gub.uy", "mrree.gub.uy", "mec.gub.uy", "mtss.gub.uy", "mvotma.gub.uy", "mgap.gub.uy", "msp.gub.uy", "mides.gub.uy"],
        priority_domains=[".gub.uy", ".uy"],
        system_prompt_suffix="searching current Uruguayan legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Uruguayan legal database. For specific legal advice, consult a qualified Uruguayan attorney."
    ),
    "PARAGUAY": JurisdictionConfig(
        name="Paraguay",
        code="PARAGUAY",
        rag_collection=None,
        official_domains=["presidencia.gov.py", "congreso.gov.py", "pj.gov.py", "bcp.gov.py", "cnv.gov.py", "set.gov.py", "ips.gov.py", "dgeec.gov.py", "tsje.gov.py", "gov.py", "hacienda.gov.py", "minterior.gov.py", "mdn.gov.py", "mre.gov.py", "mec.gov.py", "mtess.gov.py", "mades.gov.py", "mag.gov.py", "mspbs.gov.py", "mds.gov.py"],
        priority_domains=[".gov.py", ".py"],
        system_prompt_suffix="searching current Paraguayan legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Paraguayan legal database. For specific legal advice, consult a qualified Paraguayan attorney."
    ),
    "BOLIVIA": JurisdictionConfig(
        name="Bolivia",
        code="BOLIVIA",
        rag_collection=None,
        official_domains=["presidencia.gob.bo", "diputados.bo", "senado.bo", "tcpbolivia.bo", "bcb.gob.bo", "asfi.gob.bo", "impuestos.gob.bo", "afp.gob.bo", "ine.gob.bo", "oep.org.bo", "gob.bo", "economiayfinanzas.gob.bo", "mingobierno.gob.bo", "mindef.gob.bo", "cancilleria.gob.bo", "minedu.gob.bo", "mintrabajo.gob.bo", "mmaya.gob.bo", "agrobolivia.gob.bo", "minsalud.gob.bo"],
        priority_domains=[".gob.bo", ".bo"],
        system_prompt_suffix="searching current Bolivian legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Bolivian legal database. For specific legal advice, consult a qualified Bolivian attorney."
    ),
    "ECUADOR": JurisdictionConfig(
        name="Ecuador",
        code="ECUADOR",
        rag_collection=None,
        official_domains=["presidencia.gob.ec", "asambleanacional.gob.ec", "cortenacional.gob.ec", "bce.fin.ec", "superbancos.gob.ec", "sri.gob.ec", "iess.gob.ec", "inec.gob.ec", "cne.gob.ec", "gob.ec", "finanzas.gob.ec", "ministeriointerior.gob.ec", "defensa.gob.ec", "cancilleria.gob.ec", "educacion.gob.ec", "trabajo.gob.ec", "ambiente.gob.ec", "agricultura.gob.ec", "salud.gob.ec", "inclusion.gob.ec"],
        priority_domains=[".gob.ec", ".ec"],
        system_prompt_suffix="searching current Ecuadorian legal sources",
        citation_links_file=None,
        supported_languages=["es", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Ecuadorian legal database. For specific legal advice, consult a qualified Ecuadorian attorney."
    ),

    "CHINA": JurisdictionConfig(
        name="China",
        code="CHINA",
        rag_collection=None,
        official_domains=["npc.gov.cn", "court.gov.cn", "moj.gov.cn", "chinalaw.gov.cn", "pbc.gov.cn", "gov.cn", "spp.gov.cn", "mps.gov.cn", "csrc.gov.cn", "cbrc.gov.cn", "circ.gov.cn", "safe.gov.cn", "saic.gov.cn", "ndrc.gov.cn", "mof.gov.cn", "mofcom.gov.cn", "miit.gov.cn", "most.gov.cn", "mfa.gov.cn", "moe.gov.cn", "mohrss.gov.cn", "mee.gov.cn", "moa.gov.cn", "nhc.gov.cn", "mod.gov.cn"],
        priority_domains=[".gov.cn", ".cn"],
        system_prompt_suffix="searching current Chinese legal sources",
        citation_links_file=None,
        supported_languages=["zh", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Chinese legal database. For specific legal advice, consult a qualified Chinese attorney."
    ),
    "JAPAN": JurisdictionConfig(
        name="Japan",
        code="JAPAN",
        rag_collection=None,
        official_domains=["e-gov.go.jp", "sangiin.go.jp", "shugiin.go.jp", "courts.go.jp", "moj.go.jp", "boj.or.jp", "cas.go.jp", "kantei.go.jp", "fsa.go.jp", "jftc.go.jp", "mof.go.jp", "mofa.go.jp", "mext.go.jp", "mhlw.go.jp", "env.go.jp", "maff.go.jp", "meti.go.jp", "mlit.go.jp", "mod.go.jp", "npa.go.jp", "fdma.go.jp", "cao.go.jp"],
        priority_domains=[".go.jp", ".jp"],
        system_prompt_suffix="searching current Japanese legal sources",
        citation_links_file=None,
        supported_languages=["ja", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Japanese legal database. For specific legal advice, consult a qualified Japanese attorney.",
        native_legal_terms={
            "product liability": "製造物責任法",
            "contract": "契約",
            "director": "取締役"
        }
    ),
    "SOUTH_KOREA": JurisdictionConfig(
        name="South Korea",
        code="SOUTH_KOREA",
        rag_collection=None,
        official_domains=["law.go.kr", "assembly.go.kr", "scourt.go.kr", "moj.go.kr", "korea.kr", "fsc.go.kr", "bok.or.kr", "kftc.go.kr", "mosf.go.kr", "mofa.go.kr", "moe.go.kr", "moel.go.kr", "me.go.kr", "mafra.go.kr", "motie.go.kr", "molit.go.kr", "mnd.go.kr", "mois.go.kr", "mohw.go.kr", "kcdc.go.kr"],
        priority_domains=[".go.kr", ".kr"],
        system_prompt_suffix="searching current Korean legal sources",
        citation_links_file=None,
        supported_languages=["ko", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Korean legal database. For specific legal advice, consult a qualified Korean attorney."
    ),
    "INDIA": JurisdictionConfig(
        name="India",
        code="INDIA",
        rag_collection=None,
        official_domains=["indiacode.nic.in", "loksabha.nic.in", "rajyasabha.nic.in", "sci.gov.in", "lawmin.gov.in", "rbi.org.in", "sebi.gov.in", "irda.gov.in", "cci.gov.in", "cbdt.gov.in", "cbec.gov.in", "mha.gov.in", "mea.gov.in", "mhrd.gov.in", "labour.gov.in", "moef.gov.in", "agricoop.gov.in", "mohfw.gov.in", "mod.gov.in", "pmindia.gov.in", "presidentofindia.nic.in"],
        priority_domains=[".gov.in", ".nic.in"],
        system_prompt_suffix="searching current Indian legal sources",
        citation_links_file=None,
        supported_languages=["en", "hi"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Indian legal database. For specific legal advice, consult a qualified Indian advocate."
    ),
    "INDONESIA": JurisdictionConfig(
        name="Indonesia",
        code="INDONESIA",
        rag_collection=None,
        official_domains=["dpr.go.id", "mahkamahkonstitusi.go.id", "mahkamahagung.go.id", "kemenkumham.go.id", "jdih.kemenkeu.go.id", "bi.go.id", "ojk.go.id", "kppu.go.id", "kemenkeu.go.id", "kemenlu.go.id", "kemendikbud.go.id", "kemenaker.go.id", "klhk.go.id", "kementan.go.id", "kemkes.go.id", "kemhan.go.id", "kemendagri.go.id", "setkab.go.id", "bps.go.id", "kpu.go.id"],
        priority_domains=[".go.id", ".id"],
        system_prompt_suffix="searching current Indonesian legal sources",
        citation_links_file=None,
        supported_languages=["id", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Indonesian legal database. For specific legal advice, consult a qualified Indonesian attorney."
    ),
    "THAILAND": JurisdictionConfig(
        name="Thailand",
        code="THAILAND",
        rag_collection=None,
        official_domains=["parliament.go.th", "constitutionalcourt.or.th", "supremecourt.or.th", "moj.go.th", "krisdika.go.th", "bot.or.th", "sec.or.th", "oic.or.th", "mof.go.th", "mfa.go.th", "moe.go.th", "mol.go.th", "mnre.go.th", "moac.go.th", "moph.go.th", "mod.go.th", "moi.go.th", "nso.go.th", "ect.go.th"],
        priority_domains=[".go.th", ".th"],
        system_prompt_suffix="searching current Thai legal sources",
        citation_links_file=None,
        supported_languages=["th", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Thai legal database. For specific legal advice, consult a qualified Thai attorney."
    ),
    "VIETNAM": JurisdictionConfig(
        name="Vietnam",
        code="VIETNAM",
        rag_collection=None,
        official_domains=["moj.gov.vn", "quochoi.vn", "tandtc.vn", "vksndtc.gov.vn", "chinhphu.vn", "sbv.gov.vn", "ssc.gov.vn", "vcca.gov.vn", "mof.gov.vn", "mofa.gov.vn", "moet.gov.vn", "molisa.gov.vn", "monre.gov.vn", "mard.gov.vn", "moh.gov.vn", "mod.gov.vn", "mps.gov.vn", "gso.gov.vn"],
        priority_domains=[".gov.vn", ".vn"],
        system_prompt_suffix="searching current Vietnamese legal sources",
        citation_links_file=None,
        supported_languages=["vi", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Vietnamese legal database. For specific legal advice, consult a qualified Vietnamese attorney."
    ),
    "MALAYSIA": JurisdictionConfig(
        name="Malaysia",
        code="MALAYSIA",
        rag_collection=None,
        official_domains=["agc.gov.my", "parlimen.gov.my", "kehakiman.gov.my", "federalcourt.gov.my", "jpm.gov.my", "bnm.gov.my", "sc.com.my", "mycc.gov.my", "mof.gov.my", "kln.gov.my", "moe.gov.my", "mohr.gov.my", "nre.gov.my", "moa.gov.my", "moh.gov.my", "mindef.gov.my", "kdn.gov.my", "pmo.gov.my", "dosm.gov.my", "ccid.rmp.gov.my"],    
        priority_domains=[".gov.my", ".my"],
        system_prompt_suffix="searching current Malaysian legal sources",
        citation_links_file=None,
        supported_languages=["en", "ms"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Malaysian legal database. For specific legal advice, consult a qualified Malaysian advocate."
    ),
    "SINGAPORE": JurisdictionConfig(
        name="Singapore",
        code="SINGAPORE",
        rag_collection=None,
        official_domains=[
            "sso.agc.gov.sg", "agc.gov.sg", "parliament.gov.sg", "judiciary.gov.sg", 
            "supremecourt.gov.sg", "mlaw.gov.sg", "acra.gov.sg", "elitigation.sg"
        ],
        priority_domains=[
            "singaporelawwatch.sg", "lawgazette.com.sg", "singaporelegaladvice.com",
            "lawnet.sg", "sal.org.sg", "slb.sg", "lawsociety.org.sg", "plusweb.org",
            "journalsonline.academypublishing.org", "irbnet.de", "austlii.edu.au"
        ],
        system_prompt_suffix="searching current Singaporean legal sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Singaporean legal database. For specific legal advice, consult a qualified Singaporean advocate.",
        enhancement_rules={
            "business_incentives": [
                "Pioneer Certificate", "Development and Expansion Incentive", "Global Trader Programme", 
                "Headquarters Programme", "Finance and Treasury Centre", "Regional Headquarters Award",
                "Economic Development Board", "investment incentives", "tax incentives Singapore"
            ],
            "corporate_structure": [
                "private limited company", "Pte Ltd", "company incorporation", "ACRA",
                "business registration", "corporate compliance", "directors duties"
            ],
            "tax_regulations": [
                "corporate tax", "GST", "withholding tax", "double taxation agreement", 
                "tax resident", "IRAS", "tax incentives", "transfer pricing"
            ]
        },
        statutory_urls={
            "companies_act": "https://sso.agc.gov.sg/Act/COACT1967",
            "income_tax_act": "https://sso.agc.gov.sg/Act/INCTA1947",
            "gst_act": "https://sso.agc.gov.sg/Act/GSTA1993",
            "pioneer_industries_ordinance": "https://sso.agc.gov.sg/Act/PIOB1959"
        },
        known_documents={
            "pioneer_certificate": {
                "title": "Pioneer Industries (Relief from Income Tax) Act",
                "url": "https://sso.agc.gov.sg/Act/PIRITA1967",
                "verified": True,
                "priority": "high"
            },
            "edb_incentives": {
                "title": "Economic Development Board Investment Incentives", 
                "url": "https://www.edb.gov.sg/en/how-we-help/incentives-and-schemes.html",
                "verified": True,
                "priority": "high"
            },
            "companies_act": {
                "title": "Companies Act (Chapter 50)",
                "url": "https://sso.agc.gov.sg/Act/COACT1967",
                "verified": True,
                "priority": "high"
            }
        }
    ),
    "PHILIPPINES": JurisdictionConfig(
        name="Philippines",
        code="PHILIPPINES",
        rag_collection=None,
        official_domains=["op.gov.ph", "congress.gov.ph", "senate.gov.ph", "sc.judiciary.gov.ph", "doj.gov.ph", "bsp.gov.ph", "sec.gov.ph", "pcc.gov.ph", "dof.gov.ph", "dfa.gov.ph", "deped.gov.ph", "dole.gov.ph", "denr.gov.ph", "da.gov.ph", "doh.gov.ph", "dnd.gov.ph", "dilg.gov.ph", "psa.gov.ph", "comelec.gov.ph"],
        priority_domains=[".gov.ph", ".ph"],
        system_prompt_suffix="searching current Philippine legal sources",
        citation_links_file=None,
        supported_languages=["en", "fil"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Philippine legal database. For specific legal advice, consult a qualified Philippine attorney."
    ),
    "TAIWAN": JurisdictionConfig(
        name="Taiwan",
        code="TAIWAN",
        rag_collection=None,
        official_domains=["ly.gov.tw", "judicial.gov.tw", "cbc.gov.tw", "fsc.gov.tw", "ftc.gov.tw", "mof.gov.tw", "mofa.gov.tw", "moe.gov.tw", "mol.gov.tw", "moea.gov.tw", "motc.gov.tw", "mnd.gov.tw", "moi.gov.tw", "mohw.gov.tw", "ey.gov.tw", "president.gov.tw", "dgbas.gov.tw", "cec.gov.tw"],
        priority_domains=[".gov.tw", ".tw"],
        system_prompt_suffix="searching current Taiwan legal sources",
        citation_links_file=None,
        supported_languages=["zh-TW", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Taiwan legal database. For specific legal advice, consult a qualified Taiwan attorney."
    ),
    "HONG_KONG": JurisdictionConfig(
        name="Hong Kong",
        code="HONG_KONG",
        rag_collection=None,
        official_domains=["legco.gov.hk", "judiciary.hk", "hkma.gov.hk", "sfc.hk", "ia.org.hk", "cc.gov.hk", "doj.gov.hk", "fstb.gov.hk", "cmab.gov.hk", "edb.gov.hk", "labour.gov.hk", "enb.gov.hk", "devb.gov.hk", "sb.gov.hk", "hab.gov.hk", "ceo.gov.hk", "censtatd.gov.hk", "reo.gov.hk"],
        priority_domains=[".gov.hk", ".hk"],
        system_prompt_suffix="searching current Hong Kong legal sources",
        citation_links_file=None,
        supported_languages=["en", "zh-HK"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Hong Kong legal database. For specific legal advice, consult a qualified Hong Kong solicitor or barrister."
    ),
    "BANGLADESH": JurisdictionConfig(
        name="Bangladesh",
        code="BANGLADESH",
        rag_collection=None,
        official_domains=["parliament.gov.bd", "supremecourt.gov.bd", "bb.org.bd", "bsec.gov.bd", "mof.gov.bd", "mofa.gov.bd", "moedu.gov.bd", "molhr.gov.bd", "moef.gov.bd", "moa.gov.bd", "mohfw.gov.bd", "mod.gov.bd", "mopa.gov.bd", "pmo.gov.bd", "bbs.gov.bd", "ecs.gov.bd"],
        priority_domains=[".gov.bd", ".bd"],
        system_prompt_suffix="searching current Bangladesh legal sources",
        citation_links_file=None,
        supported_languages=["bn", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Bangladesh legal database. For specific legal advice, consult a qualified Bangladesh advocate."
    ),
    "PAKISTAN": JurisdictionConfig(
        name="Pakistan",
        code="PAKISTAN",
        rag_collection=None,
        official_domains=["na.gov.pk", "senate.gov.pk", "supremecourt.gov.pk", "sbp.org.pk", "secp.gov.pk", "finance.gov.pk", "mofa.gov.pk", "mofept.gov.pk", "moib.gov.pk", "mocc.gov.pk", "mod.gov.pk", "interior.gov.pk", "president.gov.pk", "pbs.gov.pk", "ecp.gov.pk"],
        priority_domains=[".gov.pk", ".pk"],
        system_prompt_suffix="searching current Pakistan legal sources",
        citation_links_file=None,
        supported_languages=["ur", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Pakistan legal database. For specific legal advice, consult a qualified Pakistan advocate."
    ),
    "SRI_LANKA": JurisdictionConfig(
        name="Sri Lanka",
        code="SRI_LANKA",
        rag_collection=None,
        official_domains=["parliament.lk", "supremecourt.lk", "cbsl.gov.lk", "sec.gov.lk", "treasury.gov.lk", "mfa.gov.lk", "moe.gov.lk", "labour.gov.lk", "mahaweli.gov.lk", "agrimin.gov.lk", "health.gov.lk", "defence.lk", "pmdiv.gov.lk", "statistics.gov.lk", "elections.gov.lk"],
        priority_domains=[".gov.lk", ".lk"],
        system_prompt_suffix="searching current Sri Lankan legal sources",
        citation_links_file=None,
        supported_languages=["si", "ta", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Sri Lankan legal database. For specific legal advice, consult a qualified Sri Lankan attorney."
    ),

    "SAUDI_ARABIA": JurisdictionConfig(
        name="Saudi Arabia",
        code="SAUDI_ARABIA",
        rag_collection=None,
        official_domains=["spa.gov.sa", "majlis.gov.sa", "saudivision2030.gov.sa", "moj.gov.sa", "boe.gov.sa", "sama.gov.sa", "cma.org.sa", "monshaat.gov.sa", "mof.gov.sa", "mofa.gov.sa", "moe.gov.sa", "mol.gov.sa", "mewa.gov.sa", "mewa.gov.sa", "moh.gov.sa", "mod.gov.sa", "moi.gov.sa", "stats.gov.sa", "nec.gov.sa"],
        priority_domains=[".gov.sa", ".sa"],
        system_prompt_suffix="searching current Saudi Arabian legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Saudi Arabian legal database. For specific legal advice, consult a qualified Saudi attorney."
    ),
    "TURKEY": JurisdictionConfig(
        name="Turkey",
        code="TURKEY",
        rag_collection=None,
        official_domains=["mevzuat.gov.tr", "tbmm.gov.tr", "anayasa.gov.tr", "yargitay.gov.tr", "adalet.gov.tr", "tcmb.gov.tr", "spk.gov.tr", "rekabet.gov.tr", "hmb.gov.tr", "mfa.gov.tr", "meb.gov.tr", "ailevecalisma.gov.tr", "csb.gov.tr", "tarimorman.gov.tr", "saglik.gov.tr", "msb.gov.tr", "icisleri.gov.tr", "tccb.gov.tr", "tuik.gov.tr", "ysk.gov.tr"],
        priority_domains=[".gov.tr", ".tr"],
        system_prompt_suffix="searching current Turkish legal sources",
        citation_links_file=None,
        supported_languages=["tr", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Turkish legal database. For specific legal advice, consult a qualified Turkish attorney."
    ),
    "IRAN": JurisdictionConfig(
        name="Iran",
        code="IRAN",
        rag_collection=None,
        official_domains=["president.ir", "majlis.ir", "divan.gov.ir", "dadgostary.gov.ir", "iranjudiciary.org", "cbi.ir", "rdif.ir", "doulat.ir", "mfa.gov.ir", "medu.ir", "mcls.gov.ir", "doe.ir", "maj.ir", "behdasht.gov.ir", "modafeaan.ir", "moi.ir", "amar.org.ir"],
        priority_domains=[".gov.ir", ".ir"],
        system_prompt_suffix="searching current Iranian legal sources",
        citation_links_file=None,
        supported_languages=["fa", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Iranian legal database. For specific legal advice, consult a qualified Iranian attorney."
    ),
    "ISRAEL": JurisdictionConfig(
        name="Israel",
        code="ISRAEL",
        rag_collection=None,
        official_domains=["main.knesset.gov.il", "supreme.court.gov.il", "justice.gov.il", "gov.il", "nevo.co.il", "boi.org.il", "isa.gov.il", "antitrust.gov.il", "mof.gov.il", "mfa.gov.il", "education.gov.il", "molsa.gov.il", "sviva.gov.il", "moag.gov.il", "health.gov.il", "mod.gov.il", "mops.gov.il", "cbs.gov.il", "bechirot.gov.il"],
        priority_domains=[".gov.il", ".il"],
        system_prompt_suffix="searching current Israeli legal sources",
        citation_links_file=None,
        supported_languages=["he", "ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Israeli legal database. For specific legal advice, consult a qualified Israeli attorney."
    ),
    "JORDAN": JurisdictionConfig(
        name="Jordan",
        code="JORDAN",
        rag_collection=None,
        official_domains=["lob.gov.jo", "jsc.gov.jo", "cbj.gov.jo", "jsc.gov.jo", "mof.gov.jo", "mfa.gov.jo", "moe.gov.jo", "mol.gov.jo", "moenv.gov.jo", "moa.gov.jo", "moh.gov.jo", "mod.gov.jo", "moi.gov.jo", "kingabdullah.jo", "dos.gov.jo", "iec.jo"],
        priority_domains=[".gov.jo", ".jo"],
        system_prompt_suffix="searching current Jordanian legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Jordanian legal database. For specific legal advice, consult a qualified Jordanian attorney."
    ),
    "LEBANON": JurisdictionConfig(
        name="Lebanon",
        code="LEBANON",
        rag_collection=None,
        official_domains=["lp.gov.lb", "justice.gov.lb", "bdl.gov.lb", "pcm.gov.lb", "foreign.gov.lb", "mehe.gov.lb", "labor.gov.lb", "moe.gov.lb", "agriculture.gov.lb", "moph.gov.lb", "defense.gov.lb", "interior.gov.lb", "presidency.gov.lb", "cas.gov.lb"],
        priority_domains=[".gov.lb", ".lb"],
        system_prompt_suffix="searching current Lebanese legal sources",
        citation_links_file=None,
        supported_languages=["ar", "fr", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Lebanese legal database. For specific legal advice, consult a qualified Lebanese attorney."
    ),
    "KUWAIT": JurisdictionConfig(
        name="Kuwait",
        code="KUWAIT",
        rag_collection=None,
        official_domains=["kna.kw", "da.gov.kw", "cbk.gov.kw", "cma.gov.kw", "mof.gov.kw", "mofa.gov.kw", "moe.gov.kw", "manpower.gov.kw", "epa.org.kw", "paaafr.gov.kw", "moh.gov.kw", "mod.gov.kw", "moi.gov.kw", "da.gov.kw", "csb.gov.kw"],
        priority_domains=[".gov.kw", ".kw"],
        system_prompt_suffix="searching current Kuwaiti legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Kuwaiti legal database. For specific legal advice, consult a qualified Kuwaiti attorney."
    ),
    "QATAR": JurisdictionConfig(
        name="Qatar",
        code="QATAR",
        rag_collection=None,
        official_domains=["majlis.qa", "sjc.gov.qa", "qcb.gov.qa", "qfcra.com", "mef.gov.qa", "mofa.gov.qa", "edu.gov.qa", "adlsa.gov.qa", "mme.gov.qa", "moph.gov.qa", "mod.gov.qa", "moi.gov.qa", "diwan.gov.qa", "psa.gov.qa"],
        priority_domains=[".gov.qa", ".qa"],
        system_prompt_suffix="searching current Qatari legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Qatari legal database. For specific legal advice, consult a qualified Qatari attorney."
    ),
    "BAHRAIN": JurisdictionConfig(
        name="Bahrain",
        code="BAHRAIN",
        rag_collection=None,
        official_domains=["nhra.bh", "legalaffairs.gov.bh", "cbb.gov.bh", "cba.gov.bh", "mof.gov.bh", "mofa.gov.bh", "education.gov.bh", "mlsd.gov.bh", "ewa.bh", "works.gov.bh", "moh.gov.bh", "mod.bh", "interior.gov.bh", "pm.gov.bh", "cio.gov.bh"],
        priority_domains=[".gov.bh", ".bh"],
        system_prompt_suffix="searching current Bahraini legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Bahraini legal database. For specific legal advice, consult a qualified Bahraini attorney."
    ),
    "OMAN": JurisdictionConfig(
        name="Oman",
        code="OMAN",
        rag_collection=None,
        official_domains=["majlis.om", "oman.om", "cbo.gov.om", "cma.gov.om", "mof.gov.om", "mofa.gov.om", "moe.gov.om", "manpower.gov.om", "meca.gov.om", "maf.gov.om", "moh.gov.om", "mod.gov.om", "rpo.gov.om", "ncsi.gov.om"],
        priority_domains=[".gov.om", ".om"],
        system_prompt_suffix="searching current Omani legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Omani legal database. For specific legal advice, consult a qualified Omani attorney."
    ),

    "SOUTH_AFRICA": JurisdictionConfig(
        name="South Africa",
        code="SOUTH_AFRICA",
        rag_collection=None,
        official_domains=["justice.gov.za", "parliament.gov.za", "concourt.org.za", "supremecourtofappeal.org.za", "doj.gov.za", "resbank.co.za", "fsca.co.za", "compcom.co.za", "treasury.gov.za", "dirco.gov.za", "dbe.gov.za", "labour.gov.za", "dffe.gov.za", "dalrrd.gov.za", "health.gov.za", "dod.mil.za", "saps.gov.za", "presidency.gov.za", "statssa.gov.za", "elections.org.za"],
        priority_domains=[".gov.za", ".za"],
        system_prompt_suffix="searching current South African legal sources",
        citation_links_file=None,
        supported_languages=["en", "af"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized South African legal database. For specific legal advice, consult a qualified South African attorney."
    ),
    "EGYPT": JurisdictionConfig(
        name="Egypt",
        code="EGYPT",
        rag_collection=None,
        official_domains=["presidency.eg", "parliament.gov.eg", "scc.gov.eg", "cc.gov.eg", "moj.gov.eg", "cbe.org.eg", "fra.gov.eg", "mof.gov.eg", "mfa.gov.eg", "moe.gov.eg", "manpower.gov.eg", "eeaa.gov.eg", "malr.gov.eg", "mohp.gov.eg", "mod.gov.eg", "moi.gov.eg", "sis.gov.eg", "capmas.gov.eg"],
        priority_domains=[".gov.eg", ".eg"],
        system_prompt_suffix="searching current Egyptian legal sources",
        citation_links_file=None,
        supported_languages=["ar", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Egyptian legal database. For specific legal advice, consult a qualified Egyptian attorney."
    ),
    "NIGERIA": JurisdictionConfig(
        name="Nigeria",
        code="NIGERIA",
        rag_collection=None,
        official_domains=["nass.gov.ng", "supremecourt.gov.ng", "justice.gov.ng", "nigerialaw.org", "lawpavilion.com", "cbn.gov.ng", "sec.gov.ng", "cac.gov.ng", "budgetoffice.gov.ng", "mfaangeria.gov.ng", "education.gov.ng", "labour.gov.ng", "environment.gov.ng", "agriculture.gov.ng", "health.gov.ng", "defence.gov.ng", "interior.gov.ng", "presidency.gov.ng", "nigerianstat.gov.ng"],
        priority_domains=[".gov.ng", ".ng"],
        system_prompt_suffix="searching current Nigerian legal sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Nigerian legal database. For specific legal advice, consult a qualified Nigerian attorney."
    ),
    "KENYA": JurisdictionConfig(
        name="Kenya",
        code="KENYA",
        rag_collection=None,
        official_domains=["parliament.go.ke", "judiciary.go.ke", "kenyalaw.org", "caj.go.ke", "ag.go.ke", "centralbank.go.ke", "cma.or.ke", "cak.or.ke", "treasury.go.ke", "mfa.go.ke", "education.go.ke", "labour.go.ke", "environment.go.ke", "agriculture.go.ke", "health.go.ke", "defence.go.ke", "interior.go.ke", "president.go.ke", "knbs.or.ke", "iebc.or.ke"],
        priority_domains=[".go.ke", ".ke"],
        system_prompt_suffix="searching current Kenyan legal sources",
        citation_links_file=None,
        supported_languages=["en", "sw"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Kenyan legal database. For specific legal advice, consult a qualified Kenyan advocate."
    ),

    "AUSTRALIA": JurisdictionConfig(
        name="Australia",
        code="AUSTRALIA",
        rag_collection=None,
        official_domains=["legislation.gov.au", "aph.gov.au", "hcourt.gov.au", "fedcourt.gov.au", "ag.gov.au", "rba.gov.au", "austlii.edu.au", "parliament.nsw.gov.au", "parliament.vic.gov.au", "parliament.qld.gov.au", "parliament.wa.gov.au", "parliament.sa.gov.au", "parliament.tas.gov.au", "parliament.act.gov.au", "parliament.nt.gov.au", "asic.gov.au", "apra.gov.au", "accc.gov.au", "treasury.gov.au", "dfat.gov.au", "education.gov.au", "employment.gov.au", "environment.gov.au", "agriculture.gov.au", "health.gov.au", "defence.gov.au", "homeaffairs.gov.au", "pm.gov.au", "abs.gov.au", "aec.gov.au"],
        priority_domains=[".gov.au", ".au"],
        system_prompt_suffix="searching current Australian legal sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Australian legal database. For specific legal advice, consult a qualified Australian barrister or solicitor."
    ),
    "NEW_ZEALAND": JurisdictionConfig(
        name="New Zealand",
        code="NEW_ZEALAND",
        rag_collection=None,
        official_domains=["legislation.govt.nz", "parliament.nz", "courtsofnz.govt.nz", "justice.govt.nz", "nzlii.org", "rbnz.govt.nz", "fma.govt.nz", "comcom.govt.nz", "treasury.govt.nz", "mfat.govt.nz", "education.govt.nz", "mbie.govt.nz", "mfe.govt.nz", "mpi.govt.nz", "health.govt.nz", "nzdf.mil.nz", "police.govt.nz", "dpmc.govt.nz", "stats.govt.nz", "elections.nz"],
        priority_domains=[".govt.nz", ".nz"],
        system_prompt_suffix="searching current New Zealand legal sources",
        citation_links_file=None,
        supported_languages=["en", "mi"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized New Zealand legal database. For specific legal advice, consult a qualified New Zealand barrister or solicitor."
    ),

    "RUSSIA": JurisdictionConfig(
        name="Russia",
        code="RUSSIA",
        rag_collection=None,
        official_domains=[

            "kremlin.ru", "government.ru", "duma.gov.ru", "council.gov.ru",

            "ksrf.ru", "vsrf.ru", "arbitr.ru", "minjust.gov.ru",

            "pravo.gov.ru", "rg.ru", 

            "cbr.ru", "nalog.gov.ru", "economy.gov.ru", "fas.gov.ru", "rosreestr.gov.ru",

            "fedresurs.ru", "fssprus.ru"
        ],
        priority_domains=[

            "consultant.ru", "garant.ru",

            "minpromtorg.ru", "rospatent.gov.ru", "rospotrebnadzor.gov.ru"
        ],
        system_prompt_suffix="searching current Russian legal sources",
        citation_links_file=None,
        supported_languages=["ru", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Russian legal database. For specific legal advice, consult a qualified Russian attorney."
    ),
    "GEORGIA": JurisdictionConfig(
        name="Georgia",
        code="GEORGIA",
        rag_collection=None,
        official_domains=["matsne.gov.ge", "parliament.ge", "supremecourt.ge", "ccourt.ge", "justice.gov.ge", "nbg.gov.ge", "rs.ge"],
        priority_domains=[".gov.ge", ".ge"],
        system_prompt_suffix="searching current Georgian legal sources",
        citation_links_file=None,
        supported_languages=["ka", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Georgian legal database. For specific legal advice, consult a qualified Georgian attorney."
    ),
    "AZERBAIJAN": JurisdictionConfig(
        name="Azerbaijan",
        code="AZERBAIJAN",
        rag_collection=None,
        official_domains=["e-qanun.az", "meclis.gov.az", "supremecourt.gov.az", "constcourt.gov.az", "justice.gov.az", "cbar.az"],
        priority_domains=[".gov.az", ".az"],
        system_prompt_suffix="searching current Azerbaijani legal sources",
        citation_links_file=None,
        supported_languages=["az", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Azerbaijani legal database. For specific legal advice, consult a qualified Azerbaijani attorney."
    ),
    "ARMENIA": JurisdictionConfig(
        name="Armenia",
        code="ARMENIA",
        rag_collection=None,
        official_domains=["arlis.am", "parliament.am", "court.am", "justice.am", "cba.am", "gov.am"],
        priority_domains=[".am", ".gov.am"],
        system_prompt_suffix="searching current Armenian legal sources",
        citation_links_file=None,
        supported_languages=["hy", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Armenian legal database. For specific legal advice, consult a qualified Armenian attorney."
    ),
    "UZBEKISTAN": JurisdictionConfig(
        name="Uzbekistan",
        code="UZBEKISTAN",
        rag_collection=None,
        official_domains=["lex.uz", "parliament.gov.uz", "supreme.court.uz", "minjust.uz", "cbu.uz", "my.gov.uz", "gov.uz", "president.uz", "constitution.uz"],
        priority_domains=[".gov.uz", ".uz"],
        system_prompt_suffix="searching current Uzbek legal sources",
        citation_links_file=None,
        supported_languages=["uz", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Uzbek legal database. For specific legal advice, consult a qualified Uzbek attorney."
    ),
    "KYRGYZSTAN": JurisdictionConfig(
        name="Kyrgyzstan",
        code="KYRGYZSTAN",
        rag_collection=None,
        official_domains=["cbd.minjust.gov.kg", "kenesh.kg", "supcourt.kg", "minjust.gov.kg", "nbkr.kg", "gov.kg"],
        priority_domains=[".gov.kg", ".kg"],
        system_prompt_suffix="searching current Kyrgyz legal sources",
        citation_links_file=None,
        supported_languages=["ky", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Kyrgyz legal database. For specific legal advice, consult a qualified Kyrgyz attorney."
    ),
    "KAZAKHSTAN": JurisdictionConfig(
        name="Kazakhstan",
        code="KAZAKHSTAN",
        rag_collection=None,
        official_domains=["adilet.zan.kz", "parlam.kz", "supremecourt.kz", "adilkz.gov.kz", "nationalbank.kz", "gov.kz"],
        priority_domains=[".gov.kz", ".kz"],
        system_prompt_suffix="searching current Kazakh legal sources",
        citation_links_file=None,
        supported_languages=["kk", "ru", "en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized Kazakh legal database. For specific legal advice, consult a qualified Kazakh attorney."
    ),

    "UK": JurisdictionConfig(
        name="United Kingdom",
        code="UK",
        rag_collection=None,
        official_domains=["legislation.gov.uk", "parliament.uk", "supremecourt.uk", "justice.gov.uk", "bankofengland.co.uk", "gov.uk", "parliament.scot", "senedd.wales", "niassembly.gov.uk", "bailii.org", "lawreports.co.uk", "judiciary.uk", "lawcom.gov.uk"],
        priority_domains=[".gov.uk", "legislation.gov.uk"],
        system_prompt_suffix="searching current UK legal sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=True,
        disclaimer_text="This information is based on online sources as I do not have a specialized UK legal database. For specific legal advice, consult a qualified UK solicitor or barrister.",
        statutory_urls={
            "england": {
                "companies_act": "https://www.legislation.gov.uk/ukpga/2006/46/contents",
                "insolvency_act": "https://www.legislation.gov.uk/ukpga/1986/45/contents"
             }
        },
        enhancement_rules={
            "england": {
                "company_queries": ["'companies act 2006'", "'articles of association'", "'companies house'"]
            }
        }
    ),
    "GENERAL": JurisdictionConfig(
        name="General",
        code="GENERAL",
        rag_collection=None,
        official_domains=["un.org", "worldbank.org", "wipo.int"],
        priority_domains=[".gov", ".org"],
        system_prompt_suffix="searching general online sources",
        citation_links_file=None,
        supported_languages=["en"],
        has_specialized_rag=False,
        has_official_search=False,                                  
        disclaimer_text="This is general information based on online sources. For specific legal advice, please consult a qualified legal professional in the relevant jurisdiction."
    )
}

def get_jurisdiction_config(jurisdiction_code: Optional[str]) -> JurisdictionConfig:
    """
    Retrieves the configuration for a given jurisdiction code.
    Falls back to the GENERAL configuration if the code is not found.
    """
    if not jurisdiction_code:
        return JURISDICTION_CONFIGS["GENERAL"]
    return JURISDICTION_CONFIGS.get(jurisdiction_code.upper(), JURISDICTION_CONFIGS["GENERAL"])

