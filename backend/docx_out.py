BUILDERS = {
    "coauthors_agreement": build_coauthors_agreement,
    "license": build_license,
    # "service": build_service_contract,
}

def build_document(doc_type: str, params: dict) -> bytes:
    builder = BUILDERS.get(doc_type)
    if builder is None:
        raise ValueError(f"Неизвестный тип договора: {doc_type}")
    return builder(params)