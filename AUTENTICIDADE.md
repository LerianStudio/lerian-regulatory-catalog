# Autenticidade do catálogo

Como um Reporter sabe que o catálogo que vai instalar foi publicado pela curadoria da
Lerian e não foi alterado no caminho. Este é o processo da **primeira versão**.

## O que garante e o que não garante

Garante que o Reporter **recusa**:

- uma release publicada por quem não é da curadoria (acesso de escrita indevido, token
  vazado, conta comprometida que não passe pela aprovação);
- um pacote alterado depois de publicado — num espelho, numa cópia, num proxy;
- uma release apresentada sob uma tag que não é a dela.

Não garante a correção do conteúdo: um documento errado publicado legitimamente passa.
Isso é papel da revisão, da homologação e do fluxo `develop → release-candidate → main`.

## Como funciona

Não há chave guardada. Quem assina é o próprio workflow de publicação, com uma
identidade que o GitHub dá a ele.

1. Uma tag `vX.Y.Z` ou `vX.Y.Z-rc.N` dispara o `.github/workflows/release.yml`.
2. O job de publicação espera a aprovação no ambiente `release`.
3. Aprovado, ele monta e confere o pacote e pede ao GitHub um **certificado de poucos
   minutos** que diz: "sou o `release.yml` do `LerianStudio/lerian-regulatory-catalog`,
   rodando na tag `<tag>`" — `vX.Y.Z` numa release, `vX.Y.Z-rc.N` numa candidata. O certificado é emitido pelo **Sigstore**, um serviço
   público de assinatura mantido pela OpenSSF.
4. O job assina o SHA-256 do pacote com esse certificado. A assinatura fica registrada
   no **log de transparência** público do Sigstore, que não aceita apagar nem reescrever
   entradas. O certificado expira em seguida e não serve para assinar mais nada; ele
   continua dentro do atestado, onde prova quem assinou aquela vez.
5. O resultado — o **atestado** — é anexado à release como
   `catalog-X.Y.Z.tar.gz.sigstore.json`, ao lado do pacote. O job confere o atestado
   com a mesma identidade que o Reporter exige antes de publicar.
6. O Reporter, ao assinar ou adotar um documento, baixa o atestado e o pacote e só
   instala a release quando o atestado prova, ao mesmo tempo:
   - que foi feito por **este** workflow (`release.yml`) **deste** repositório;
   - para **a tag desta** release;
   - sobre **estes** bytes;
   - e que está no log do Sigstore.

A **conferência** não acessa a internet: a raiz de confiança do Sigstore vai embutida
no Reporter, e o horário do log, que vem dentro do atestado, prova que o certificado
estava válido quando a assinatura foi feita. O Reporter continua precisando alcançar o
GitHub para **baixar** a release e o atestado — exatamente o acesso que já tem hoje;
nada além disso.

## Um atestado por release

Cada release tem **um** atestado, que cobre o pacote inteiro — todos os documentos dela,
mudados ou não naquela versão. O pacote carrega o manifesto com o SHA-256 de cada
arquivo, e o Reporter confere cada arquivo contra ele; o atestado garante o pacote, e
portanto o manifesto e cada documento. Uma release nova sempre ganha atestado novo.

## Configuração do repositório

Feita uma vez, por um administrador:

**Proteção das tags `v*`** — duas regras, porque são duas garantias diferentes:

1. **Criar** uma tag de release é só para administradores:

   ```bash
   gh api -X POST repos/LerianStudio/lerian-regulatory-catalog/rulesets --input - <<'EOF'
   {
     "name": "release-tags-creation",
     "target": "tag",
     "enforcement": "active",
     "conditions": { "ref_name": { "include": ["refs/tags/v*"], "exclude": [] } },
     "rules": [{ "type": "creation" }],
     "bypass_actors": [{ "actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always" }]
   }
   EOF
   ```

2. **Mover ou apagar** uma tag publicada é para ninguém — nem administradores, por isso
   esta regra não tem exceção:

   ```bash
   gh api -X POST repos/LerianStudio/lerian-regulatory-catalog/rulesets --input - <<'EOF'
   {
     "name": "release-tags-immutable",
     "target": "tag",
     "enforcement": "active",
     "conditions": { "ref_name": { "include": ["refs/tags/v*"], "exclude": [] } },
     "rules": [{ "type": "update" }, { "type": "deletion" }],
     "bypass_actors": []
   }
   EOF
   ```

   Uma tag errada não é corrigida: publica-se a versão seguinte.

   **O limite destas regras são os administradores do repositório.** Quem administra o
   repositório pode editar ou desativar uma regra antes de mexer numa tag, e cada
   mudança numa regra fica registrada no log de auditoria do repositório. Por isso a
   lista de administradores é curta e é ela que se confia. Se for preciso resistir até
   a um administrador comprometido, as mesmas duas regras viram regras da organização,
   geridas só pelos proprietários da organização.

**Ambiente `release`** — em *Settings → Environments → release*:

- *Required reviewers*: quem aprova uma publicação;
- *Prevent self-review*: marcado, para que quem criou a tag não aprove sozinho;
- *Allow administrators to bypass configured protection rules*: **desmarcado** — o
  GitHub deixa marcado por padrão, e com ele um administrador publica sem aprovação;
- *Deployment branches and tags*: apenas tags `v*`.

Não há segredo para cadastrar.

## O que é contrato com o Reporter

Mudar qualquer um destes aqui faz **toda** release ser recusada até o Reporter mudar
junto (`pkg/reporter/catalog/attestation.go`):

- o caminho do workflow: `.github/workflows/release.yml`;
- o repositório: `LerianStudio/lerian-regulatory-catalog`;
- a publicação a partir de uma **tag** (a identidade é `release.yml@refs/tags/<tag>`);
- o nome do anexo: `<pacote>.sigstore.json`.

## Como o Reporter trata cada origem

| Origem | Uso | Conferência |
|---|---|---|
| Releases do GitHub (`REGULATORY_CATALOG_GITHUB_REPO`) | staging, produção, clientes com internet | exige o atestado; sem ele, ou com um que não confere, recusa (`RPT-0154`) |
| Diretório montado (`REGULATORY_CATALOG_DIR`) | desenvolvimento e homologação local | não confere: a árvore já chega aberta. Não é caminho de produção |

## Ordem de implantação

O Reporter que exige o atestado só pode chegar a um ambiente **depois** que a release que
esse ambiente lê estiver atestada. Antes disso ele recusaria a release sem atestado ao
assinar ou adotar um documento (o que já está materializado continua gerando: a geração
não toca o catálogo).

1. Este workflow entra na `develop` e segue para a `release-candidate`.
2. Uma rc é publicada atestada.
3. O Reporter que exige o atestado sobe no staging.
4. Para produção, o mesmo: a release da `main` atestada antes do Reporter.

## Quando algo dá errado

| Situação | O que acontece | O que fazer |
|---|---|---|
| Sigstore fora do ar na publicação | o job falha antes de publicar | rodar o job de novo |
| O atestado não confere no próprio job | o job falha antes de publicar | investigar; nada foi publicado |
| Release publicada sem atestado (por fora do workflow) | todo Reporter recusa | apagar a release e publicar a versão seguinte pelo workflow (a tag não é reaproveitada) |
| Suspeita de publicação indevida | aparece no log público do Sigstore e na aba *Attestations* do repositório | revogar acessos, apagar a release, publicar a versão seguinte pelo fluxo |
| O Sigstore troca a raiz de confiança (escala de anos) | releases novas deixam de conferir num Reporter antigo | versão do Reporter com a raiz nova antes da troca valer |

## Conferir à mão

Qualquer pessoa confere uma release com o `gh`:

```bash
gh release download vX.Y.Z -R LerianStudio/lerian-regulatory-catalog
gh attestation verify catalog-X.Y.Z.tar.gz \
  --bundle catalog-X.Y.Z.tar.gz.sigstore.json \
  --repo LerianStudio/lerian-regulatory-catalog \
  --cert-identity "https://github.com/LerianStudio/lerian-regulatory-catalog/.github/workflows/release.yml@refs/tags/vX.Y.Z" \
  --cert-oidc-issuer https://token.actions.githubusercontent.com
```

## Fora desta versão

- **Pacote offline conferido**: um cliente sem internet que recebe o `.tar.gz` e o
  `.sigstore.json` e aponta o Reporter para eles, com a mesma conferência. Entra quando
  houver o primeiro cliente sem internet.
- **Atualização automática da raiz do Sigstore** pelo Reporter: exigiria liberar acesso
  de rede ao Sigstore em cada ambiente.
