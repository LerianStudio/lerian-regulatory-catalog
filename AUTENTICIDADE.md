# Autenticidade do catálogo

Como um Reporter sabe que o catálogo que vai instalar foi publicado pela curadoria da
Lerian e não foi alterado no caminho. Este é o processo da **primeira versão**.

## O que garante e o que não garante

Garante que o Reporter **recusa**:

- uma release publicada fora do workflow de publicação deste repositório (acesso de
  escrita indevido, token vazado);
- um pacote alterado depois de publicado — num espelho, numa cópia, num proxy;
- uma release apresentada sob uma tag que não é a dela.

Não garante a correção do conteúdo: um documento errado publicado legitimamente passa.
Isso é papel da revisão, da homologação e do fluxo `develop → release-candidate → main`.

## Como funciona

Não há chave guardada. Quem assina é o próprio workflow de publicação, com uma
identidade que o GitHub dá a ele.

1. Um PR aprovado é mergeado numa das três branches. O job `tag` do
   `.github/workflows/release.yml` calcula a versão (semantic-release) e empurra a tag:
   `vX.Y.Z-beta.N` da `develop`, `vX.Y.Z-rc.N` da `release-candidate`, `vX.Y.Z` da
   `main`. Ninguém cria tag à mão.
2. A tag dispara o mesmo workflow, agora no job `publish`, que confere que a tag aponta
   para um commit da sua branch, monta e confere o pacote e pede ao GitHub um
   **certificado de poucos minutos** que diz: "sou o `release.yml` do
   `LerianStudio/lerian-regulatory-catalog`, rodando na tag `<tag>`". O certificado é
   emitido pelo **Sigstore**, um serviço público de assinatura mantido pela OpenSSF.
3. O job assina o SHA-256 do pacote com esse certificado. A assinatura fica registrada
   no **log de transparência** público do Sigstore, que não aceita apagar nem reescrever
   entradas. O certificado expira em seguida e não serve para assinar mais nada; ele
   continua dentro do atestado, onde prova quem assinou aquela vez.
4. O resultado — o **atestado** — é anexado à release como
   `catalog-X.Y.Z.tar.gz.sigstore.json`, ao lado do pacote. O job confere o atestado
   com a mesma identidade que o Reporter exige antes de publicar.
5. O Reporter, ao assinar ou adotar um documento, baixa o atestado e o pacote e só
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

## Onde está o controle

Não há regra de tag nem ambiente de aprovação: o catálogo segue o mesmo padrão dos
demais repositórios da Lerian. O controle está em três pontos, e nenhum depende de
uma chave:

- **a revisão do PR** — conteúdo só chega à `release-candidate` e à `main` com PR
  aprovado, como em todo repositório;
- **a tag só publica conteúdo já mergeado** — o job `publish` recusa uma tag cujo
  commit não está na branch do seu formato. Mesmo uma tag criada à mão por quem tem
  acesso de escrita só publica o que já passou pela revisão;
- **o atestado** — prova que foi este workflow, já revisado, que publicou aqueles
  bytes. Um pacote alterado depois é recusado pelo Reporter.

O que fica descoberto é menor e está registrado: quem tem acesso de escrita pode criar
uma tag fora de hora (sobre conteúdo já revisado) ou mover e apagar uma tag (a release
publicada e o seu atestado não mudam com isso). A lista de quem tem acesso de escrita é,
por isso, a fronteira de confiança.

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
| Releases do GitHub (`REGULATORY_CATALOG_GITHUB_REPO`) | dev, staging, produção, clientes com internet | exige o atestado; sem ele, ou com um que não confere, recusa (`RPT-0154`) |
| Diretório montado (`REGULATORY_CATALOG_DIR`) | desenvolvimento e homologação local | não confere: a árvore já chega aberta. Não é caminho de produção |

Cada ambiente lê só o seu tipo de release (`REGULATORY_CATALOG_CHANNEL`):

| Canal | Lê | Ambiente |
|---|---|---|
| `beta` | a mais nova de qualquer tipo | dev |
| `rc` | a candidata ou release mais nova, nunca uma beta | staging |
| `stable` (padrão) | só a release `vX.Y.Z` | produção |

## Ordem de implantação

O Reporter que exige o atestado só pode chegar a um ambiente **depois** que a release que
esse ambiente lê estiver atestada. Antes disso ele recusaria a release sem atestado ao
assinar ou adotar um documento (o que já está materializado continua gerando: a geração
não toca o catálogo).

1. Este workflow entra na `develop`; o merge publica a primeira beta atestada.
2. A `develop` vai para a `release-candidate`; o merge publica a primeira rc atestada.
3. O Reporter que exige o atestado sobe no staging, com `REGULATORY_CATALOG_CHANNEL=rc`.
4. Para produção, o mesmo: a release da `main` atestada antes do Reporter.

As releases publicadas antes deste workflow (`v1.0.0-rc.1`, `v1.0.0-beta.1`) não têm
atestado e são recusadas; ficam como histórico.

## Quando algo dá errado

| Situação | O que acontece | O que fazer |
|---|---|---|
| Sigstore fora do ar na publicação | o job falha antes de publicar | rodar o job de novo |
| O atestado não confere no próprio job | o job falha antes de publicar | investigar; nada foi publicado |
| O `publish` falhou depois de a tag existir | a tag fica sem release; o Reporter segue lendo a anterior do canal | rodar o job da tag de novo; se o problema for do conteúdo, corrigir por PR, que gera a versão seguinte |
| O `publish` falhou no meio da publicação (release criada, anexos incompletos) | a release existe sem algum dos cinco anexos (pacote, `.sigstore.json`, `SHA256SUMS`, `LICENSE`, `NOTICE`); é a mais nova do canal, e o Reporter a recusa | conferir os anexos com `gh release view <tag>`; se faltar algum, apagar a release (`gh release delete <tag>`, mantendo a tag) e rodar o job da tag de novo |
| Release publicada sem atestado (por fora do workflow) | todo Reporter recusa | apagar a release; o próximo merge publica a versão seguinte |
| Suspeita de publicação indevida | aparece no log público do Sigstore e na aba *Attestations* do repositório | revogar acessos, apagar a release; o próximo merge publica a versão seguinte |
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
