<table border="0" cellspacing="0" cellpadding="0">
  <tr>
    <td><img src="https://github.com/LerianStudio.png" width="72" alt="Lerian" /></td>
    <td><h1>Lerian Regulatory Catalog</h1></td>
  </tr>
</table>

---

## Description

<!-- Summarize what this PR changes and why. Name the document(s) affected
     (e.g. Cadoc 4010) and link the primary source — the regulator's layout
     manual or XSD — the change was checked against. -->

## Type of Change

- [ ] `feat`: New feature or capability
- [ ] `fix`: Bug fix
- [ ] `perf`: Performance improvement
- [ ] `refactor`: Internal restructuring with no behavior change
- [ ] `docs`: Documentation only (README, docs/, llms.txt, inline comments)
- [ ] `style`: Formatting, whitespace, naming (no logic change)
- [ ] `test`: Adding or updating tests
- [ ] `ci`: CI pipeline or workflow changes
- [ ] `build`: Build system, Dockerfile, Go module dependencies
- [ ] `chore`: Maintenance, config, tooling
- [ ] `revert`: Reverts a previous commit
- [ ] `BREAKING CHANGE`: Consumers must update their integration

## Breaking Changes

<!-- If applicable, describe exactly what breaks (env vars, route paths,
     persistence schema, public ports/adapters) and how downstream services
     should migrate. Remove this section if not applicable. -->

None.

## Testing

- [ ] `python3 tools/test_validate.py` and `python3 tools/test_natureza.py` pass
- [ ] `python3 tools/validate.py` passes
- [ ] `python3 tools/test_release.py` passes if packaging changed
- [ ] `tools/release.py build` and `tools/release.py verify` succeed locally if `catalog.yaml` or a published document changed
- [ ] Homologation scenarios (`tools/homologation/`) re-run against Midaz if a contract or template changed

**Test evidence / Actions run:** <!-- Optional: link to a CI run or homologation output -->

## Curation Checklist

- [ ] Worked from the primary source and recorded it in `metadata.sourceOfTruth`
- [ ] Contract written before the template — the template uses no field the contract does not declare
- [ ] Format, scale, sign and domain live only in the contract, never repeated in the template
- [ ] Every rule declares a `severity`, with the reason in its message
- [ ] Every multi-row set that does not hang from another declares its `consolidation`
- [ ] `metadata.version` of each touched document bumped by the patch/minor/major rule, and `catalog.yaml` kept in sync
- [ ] `contract.yaml`, `template.tpl` and `binding.example.yaml` keep their names (they are a contract with the Reporter)
- [ ] A reviewer who knows the document checked the contract against the primary source, field by field

## Related Issues

Closes #
