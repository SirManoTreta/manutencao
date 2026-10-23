from dataclasses import dataclass

PROFILE_A = "A"   # Infantil 2–5 + 1º–4º
PROFILE_B = "B"   # 5º–9º + 1ª–3ª série
PROFILE_C = "C"   # Administrativo


@dataclass(frozen=True)
class PeripheralDef:
    code: str
    label: str
    has_quantity: bool = False  # usado só para CABO_RCA nos perfis A/B


CORE = [
    PeripheralDef("MOUSE", "Mouse"),
    PeripheralDef("TECLADO", "Teclado"),
    PeripheralDef("TELA", "Tela"),
]

EDU_SHARED = [
    PeripheralDef("AMPLIFICADOR", "Amplificador"),
    PeripheralDef("MICROFONE", "Microfone"),
    PeripheralDef("CABO_MICROFONE", "Cabo Microfone"),
    PeripheralDef("CABO_RCA", "Cabo RCA", has_quantity=True),  # A/B: terá quantidade
    PeripheralDef("CAMERA_EAD", "Câmera para EAD"),
]

PROFILE_A_ONLY = [
    PeripheralDef("PROJETOR", "Projetor"),
    PeripheralDef("CONTROLE_PROJETOR", "Controle projetor"),
    PeripheralDef("ESTOJO_CANETAS", "Estojo canetas"),
    PeripheralDef("CANETAS_PROJETOR", "Canetas projetor"),
]

PROFILE_B_ONLY = [
    PeripheralDef("TELA_INTERATIVA", "Tela Interativa"),
    PeripheralDef("CONTROLE_TELA", "Controle tela"),
    PeripheralDef("CANETA_TELA_INTERATIVA", "Caneta Tela Interativa"),
]

ADMIN_ONLY = [
    PeripheralDef("CAIXA_SOM", "Caixa de som"),
    PeripheralDef("FONE_OUVIDO", "Fone de ouvido"),
    PeripheralDef("WEBCAM", "Web cam"),
]


def peripherals_for_profile(profile: str) -> list[PeripheralDef]:
    if profile == PROFILE_A:
        return CORE + EDU_SHARED + PROFILE_A_ONLY
    if profile == PROFILE_B:
        return CORE + EDU_SHARED + PROFILE_B_ONLY
    if profile == PROFILE_C:
        # Administrativo: CORE + itens próprios (sem amplificador/microfone/cabos/câmeras/projetor)
        return CORE + ADMIN_ONLY
    return CORE
