"""Broker MQTT de test (broker_dev.py) : jokers, messages retenus, Last Will, accusés de réception.

Pas de socket : les paquets MQTT sont écrits à la main et le broker répond dans un faux writer.
"""
import asyncio
import struct

import broker_dev
import pytest

CONNACK, PUBLISH, PUBACK, SUBACK, UNSUBACK, PINGRESP = 2, 3, 4, 9, 11, 13


class FauxWriter:
    """Remplace l'asyncio.StreamWriter d'un client : garde les octets que le broker lui envoie."""

    def __init__(self):
        self.recu = bytearray()
        self.ferme = False

    def write(self, donnees):
        self.recu += donnees

    def is_closing(self):
        return self.ferme

    def close(self):
        self.ferme = True


def chaine(texte):
    octets = texte.encode() if isinstance(texte, str) else texte
    return struct.pack("!H", len(octets)) + octets


def paquet(premier_octet, corps):
    return bytes([premier_octet]) + broker_dev.taille_restante(len(corps)) + corps


def connect(identifiant, will=None, keepalive=60):
    """Paquet CONNECT (MQTT 3.1.1, clean session). will = (topic, message, retenu)."""
    drapeaux, suite = 0x02, b""
    if will:
        topic, message, retenu = will
        drapeaux |= 0x04 | (0x20 if retenu else 0)
        suite = chaine(topic) + chaine(message)
    return paquet(0x10, chaine("MQTT") + bytes([4, drapeaux]) + struct.pack("!H", keepalive) + chaine(identifiant) + suite)


def publish(topic, message, qos=0, retenu=False, id_paquet=7):
    corps = chaine(topic) + (struct.pack("!H", id_paquet) if qos else b"") + message
    return paquet(0x30 | (qos << 1) | (1 if retenu else 0), corps)


def subscribe(*filtres, id_paquet=1):
    return paquet(0x82, struct.pack("!H", id_paquet) + b"".join(chaine(f) + b"\x00" for f in filtres))


def lire_paquets(octets):
    """Découpe les octets reçus en [(type, drapeaux, corps)]."""
    paquets, pos = [], 0
    while pos < len(octets):
        entete, taille, mult = octets[pos], 0, 1
        pos += 1
        while True:
            octet = octets[pos]
            pos += 1
            taille += (octet & 127) * mult
            mult *= 128
            if not octet & 128:
                break
        paquets.append((entete >> 4, entete & 15, bytes(octets[pos:pos + taille])))
        pos += taille
    return paquets


def publications(writer):
    """[(topic, message, retenu)] des PUBLISH reçus par ce client."""
    resultat = []
    for genre, drapeaux, corps in lire_paquets(writer.recu):
        if genre == PUBLISH:
            topic, pos = broker_dev.chaine(corps, 0)
            resultat.append((topic.decode(), corps[pos:], bool(drapeaux & 1)))
    return resultat


@pytest.fixture
def broker():
    return broker_dev.Broker()


@pytest.fixture
def client(broker):
    """client("rpi1", "iot/#") : un client connecté et abonné à ces filtres. Renvoie (Client, FauxWriter)."""
    def creer(identifiant, *filtres, will=None):
        writer = FauxWriter()
        c = broker_dev.Client(writer)
        broker.connect(c, connect(identifiant, will)[2:])
        if filtres:
            broker.subscribe(c, subscribe(*filtres)[2:])
        writer.recu.clear()
        return c, writer
    return creer


def corps(paquet_complet):
    """Le corps d'un paquet construit ici (ses tailles tiennent sur un octet)."""
    return paquet_complet[2:]


# --- Jokers -------------------------------------------------------------------


@pytest.mark.parametrize(("filtre", "topic", "attendu"), [
    ("iot/partie/etat", "iot/partie/etat", True),
    ("iot/partie/etat", "iot/partie/parole", False),
    ("iot/joueurs/+", "iot/joueurs/rpi1", True),
    ("iot/joueurs/+", "iot/joueurs", False),
    ("iot/joueurs/+", "iot/joueurs/rpi1/x", False),
    ("iot/capteurs/+/temperature", "iot/capteurs/rpi2/temperature", True),
    ("iot/capteurs/+/temperature", "iot/capteurs/rpi2/humidite", False),
    ("iot/#", "iot/role/rpi1", True),
    ("iot/#", "iot", True),          # sport/# correspond aussi à sport (MQTT 3.1.1, 4.7.1.2)
    ("#", "iot/partie/etat", True),
    ("#", "$SYS/broker/uptime", False),
    ("+/partie/etat", "$SYS/partie/etat", False),
    ("iot/+", "iot/partie/etat", False),
])
def test_correspondance_des_jokers(filtre, topic, attendu):
    assert broker_dev.correspond(filtre, topic) is attendu


# --- Encodage -----------------------------------------------------------------


@pytest.mark.parametrize(("taille", "octets"), [
    (0, b"\x00"), (127, b"\x7f"), (128, b"\x80\x01"), (16383, b"\xff\x7f"), (16384, b"\x80\x80\x01"),
])
def test_taille_restante(taille, octets):
    assert broker_dev.taille_restante(taille) == octets


def test_paquet_publish_retenu():
    assert broker_dev.paquet_publish("a/b", b"x", True) == b"\x31\x06\x00\x03a/bx"


def test_paquet_publish_long_message():
    paquet_long = broker_dev.paquet_publish("t", b"x" * 300, False)

    assert lire_paquets(paquet_long) == [(PUBLISH, 0, b"\x00\x01t" + b"x" * 300)]


# --- Connexion ----------------------------------------------------------------


def test_connexion_acceptee(broker):
    writer = FauxWriter()
    c = broker_dev.Client(writer)

    broker.connect(c, corps(connect("rpi1")))

    assert bytes(writer.recu) == b"\x20\x02\x00\x00"
    assert broker.clients == {"rpi1": c}


def test_connexion_lit_le_keepalive(broker):
    c = broker_dev.Client(FauxWriter())

    broker.connect(c, corps(connect("rpi1", keepalive=30)))

    assert c.keepalive == 30


def test_connexion_lit_le_last_will(broker):
    c = broker_dev.Client(FauxWriter())

    broker.connect(c, corps(connect("rpi1", will=("iot/joueurs/rpi1", b'{"en_ligne": false}', True))))

    assert c.will == ("iot/joueurs/rpi1", b'{"en_ligne": false}', True)


def test_connexion_sans_identifiant(broker):
    c = broker_dev.Client(FauxWriter())

    broker.connect(c, corps(connect("")))

    assert c.id.startswith("anonyme-")


def test_meme_identifiant_remplace_l_ancien_client(broker, client):
    _, ancien_writer = client("maitre-du-jeu")

    nouveau, _ = client("maitre-du-jeu")

    assert ancien_writer.ferme
    assert broker.clients["maitre-du-jeu"] is nouveau


# --- Publication --------------------------------------------------------------


def test_publication_livree_aux_abonnes_concernes(broker, client):
    emetteur, _ = client("rpi1")
    _, abonne = client("interface", "iot/votes/+")
    _, autre = client("rpi2", "iot/chat/+")

    broker.publish(emetteur, 0, corps(publish("iot/votes/rpi1", b'{"suspect": "rpi3"}')))

    assert publications(abonne) == [("iot/votes/rpi1", b'{"suspect": "rpi3"}', False)]
    assert publications(autre) == []


def test_publication_qos1_est_acquittee(broker, client):
    emetteur, writer = client("rpi1")
    paquet_qos1 = publish("iot/votes/rpi1", b"{}", qos=1, id_paquet=0x1234)

    broker.publish(emetteur, paquet_qos1[0] & 15, corps(paquet_qos1))

    assert lire_paquets(writer.recu) == [(PUBACK, 0, b"\x12\x34")]


def test_publication_qos1_ne_garde_pas_l_identifiant_dans_le_message(broker, client):
    emetteur, _ = client("rpi1")
    _, abonne = client("interface", "iot/#")
    paquet_qos1 = publish("iot/chat/rpi1", b'{"text": "salut"}', qos=1)

    broker.publish(emetteur, paquet_qos1[0] & 15, corps(paquet_qos1))

    assert publications(abonne) == [("iot/chat/rpi1", b'{"text": "salut"}', False)]


def test_message_retenu_envoye_a_un_nouvel_abonne(broker, client):
    emetteur, _ = client("maitre-du-jeu")
    paquet_retenu = publish("iot/partie/etat", b'{"etat": "vote"}', retenu=True)
    broker.publish(emetteur, paquet_retenu[0] & 15, corps(paquet_retenu))

    abonne, writer = client("interface")
    broker.subscribe(abonne, corps(subscribe("iot/partie/+")))

    assert publications(writer) == [("iot/partie/etat", b'{"etat": "vote"}', True)]


def test_message_retenu_remplace_le_precedent(broker):
    for etat in (b'{"etat": "mesures"}', b'{"etat": "debat"}'):
        broker.diffuser("iot/partie/etat", etat, True)

    assert broker.retenus == {"iot/partie/etat": b'{"etat": "debat"}'}


def test_message_retenu_vide_l_efface(broker):
    broker.diffuser("iot/partie/resultat", b'{"gagnant": "espion"}', True)

    broker.diffuser("iot/partie/resultat", b"", True)

    assert broker.retenus == {}


def test_message_non_retenu_n_est_pas_garde(broker):
    broker.diffuser("iot/votes/rpi1", b"{}", False)

    assert broker.retenus == {}


def test_publication_en_direct_sans_drapeau_retenu(broker, client):
    # Un abonné déjà là reçoit le message comme neuf, même s'il est retenu (MQTT 3.1.1, 3.3.1.3)
    _, abonne = client("interface", "iot/partie/etat")

    broker.diffuser("iot/partie/etat", b'{"etat": "vote"}', True)

    assert publications(abonne) == [("iot/partie/etat", b'{"etat": "vote"}', False)]


# --- Abonnements --------------------------------------------------------------


def test_abonnement_acquitte_chaque_filtre(broker, client):
    c, writer = client("rpi1")

    broker.subscribe(c, corps(subscribe("iot/joueurs/+", "iot/partie/etat", id_paquet=0x0102)))

    assert lire_paquets(writer.recu) == [(SUBACK, 0, b"\x01\x02\x00\x00")]
    assert c.filtres == {"iot/joueurs/+", "iot/partie/etat"}


def test_desabonnement_arrete_la_livraison(broker, client):
    c, writer = client("rpi1", "iot/chat/+")

    broker.unsubscribe(c, b"\x00\x05" + chaine("iot/chat/+"))
    broker.diffuser("iot/chat/rpi2", b"{}", False)

    assert lire_paquets(writer.recu) == [(UNSUBACK, 0, b"\x00\x05")]


# --- Boucle d'un client (gerer) : Last Will et déconnexion ---------------------


def jouer_session(broker, octets):
    """Fait lire ces octets au broker comme une connexion TCP, puis la coupe. Renvoie le FauxWriter du client."""
    async def session():
        lecteur = asyncio.StreamReader()
        lecteur.feed_data(octets)
        lecteur.feed_eof()
        writer = FauxWriter()
        await broker.gerer(lecteur, writer)
        return writer
    return asyncio.run(session())


def test_coupure_sans_disconnect_publie_le_last_will(broker, client):
    _, interface = client("interface", "iot/joueurs/+")

    jouer_session(broker, connect("rpi1", will=("iot/joueurs/rpi1", b'{"en_ligne": false}', False)))

    assert publications(interface) == [("iot/joueurs/rpi1", b'{"en_ligne": false}', False)]


def test_last_will_retenu_est_garde_pour_les_suivants(broker):
    jouer_session(broker, connect("maitre-du-jeu", will=("iot/partie/etat", b'{"etat": "arret"}', True)))

    assert broker.retenus == {"iot/partie/etat": b'{"etat": "arret"}'}


def test_disconnect_propre_ne_publie_pas_le_last_will(broker, client):
    _, interface = client("interface", "iot/joueurs/+")

    jouer_session(broker, connect("rpi1", will=("iot/joueurs/rpi1", b"{}", False)) + b"\xe0\x00")

    assert publications(interface) == []


def test_client_parti_est_retire(broker):
    writer = jouer_session(broker, connect("rpi1"))

    assert broker.clients == {}
    assert writer.ferme


def test_ping_recoit_une_reponse(broker):
    writer = jouer_session(broker, connect("rpi1") + b"\xc0\x00")

    assert [genre for genre, _, _ in lire_paquets(writer.recu)] == [CONNACK, PINGRESP]


def test_session_complete_publie_et_recoit(broker):
    octets = connect("rpi1") + subscribe("iot/chat/+") + publish("iot/chat/rpi1", b'{"text": "salut"}') + b"\xe0\x00"

    writer = jouer_session(broker, octets)

    assert publications(writer) == [("iot/chat/rpi1", b'{"text": "salut"}', False)]


def test_paquet_tronque_ne_plante_pas(broker):
    writer = jouer_session(broker, connect("rpi1")[:5])

    assert writer.ferme
