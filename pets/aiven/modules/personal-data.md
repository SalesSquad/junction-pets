## Personal and health data

- Classify data: none, internal, personal, or special category (health data is
  special category under GDPR). Put the class in `governance.data_classification`.
- Residency: keep EU personal data in EU regions; name the region for every
  proposal; never propose a non-EU replica, backup or model endpoint for it. Finnish
  health and social data also fall under secondary-use rules (Findata).
- Pseudonymisation is not anonymisation: unsalted hashes of identity codes
  (henkilötunnus) are reversible by enumeration; use a keyed HMAC with a separately
  held key, or tokenisation. Free text (clinician notes) can re-identify people
  even when identifiers are removed.
- Deleting or retaining personal data needs the data owner and the data protection
  officer (DPO); check legal retention before deletion; prefer index lifecycle
  policies over ad-hoc deletes.
- New processing of special-category data (health) with new technology (an LLM,
  a new analytics store) needs a DPIA (GDPR Art. 35) before go-live; name it.
- Sending personal data to any model (Aiven AI gateway included) needs a legal
  basis, processor terms (DPA), the provider's region, retention and DPO sign-off;
  offer synthetic or aggregate data first. A demo or mentor opinion is not clinical
  validation, and an assistant summary is not a diagnostic or treatment tool.
