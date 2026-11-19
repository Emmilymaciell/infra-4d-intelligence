# Interoperabilidade verificada

Última continuação: [OAE196 e retorno de FCStd existente](interop/FREECAD-OAE-RETORNO.md).
196 peças paramétricas reais em seis atividades; STEP196 sólidos reimportado;
malha nativa federada com propriedades por peça. 108 IDs da publicação preservados.
GUI CAD continua não observada. Os blocos abaixo descrevem as provas anteriores.

Nova prova de 14/11: [FreeCAD portátil paramétrico](interop/FREECAD-PARAMETRICO.md),
sem instalador Windows. Três peças/IDs realmente salvos e reabertos no FCStd;
108 IDs da publicação conservados no JSON. STEP reimportado, retorno publicado
em cópia pela API e altura editada de 1,25 m observada no WebGL. Resultados
completos desta nova rodada no topo do STATE; contagens anteriores abaixo são
históricas e não substituem a validação do incremento atual.

Atualização de 14/11: Chrome 214 PASS e Edge 220 PASS nos arquivos reais, sem
falhas. O Edge comprovou a malha e o GLB Blender com 108 IDs e espessura editada
0,5 m, além da publicação em cópia. Evidências no pacote `09-evidencias/`.
Essas contagens cobrem o e2e completo de interface; a suíte pytest é registrada
separadamente no STATE. Nenhuma dessas provas corresponde a GUI nativa manual.

Referência em 13/11/2026: [matriz de retornos reais](interop/MATRIZ-ROUNDTRIP-REAL.md) e [contratos](interop/CONTRATOS-ADAPTADORES.md).

| Programa | Nível alcançado nesta rodada | Próximo nível |
|---|---|---|
| QGIS 3.40.14 | Edição + salvamento + reabertura + retorno testados **via API oficial**, 108 IDs preservados | Observar GUI e obter revisão de engenheiro |
| Blender 5.2.3 LTS | Edição + salvamento + reabertura + retorno testados **via bpy/aplicativo oficial**, BLEND e GLB reais | Observar GUI; autoria IFC no Bonsai é fluxo separado |
| Excel COM16 | Planilha real aberta/editada/salva/reaberta; fórmulas recalculadas pelo aplicativo | Revisar planilha no contexto do piloto; retorno automatizado futuro |
| Bonsai | Formato IFC gerado; aplicativo não comprovado | Autorizar instalação, testar abrir/editar/salvar/reimportar |
| ProjectLibre | Formatos XML/XER gerados; aplicativo não comprovado; ZIP/JAR portátil investigado | Ensaiar runtime Java isolado e leitor/escritor nativo, sem presumir POD |
| FreeCAD 1.1.4 portátil | Três Part::Box em FCStd, editar Height, salvar/reabrir, STEP reimportado e retorno real de malha pela API/WebGL | Observar GUI e ensaiar autoria mais abrangente com engenheiro |
| LibreOffice Calc | Arquivos de troca disponíveis; aplicativo não comprovado | Autorizar/identificar instalação e validar fórmulas |
| P6, Project, Revit, Navisworks, Civil 3D, OpenRail | Não homologados | Conferir licença adequada e testar arquivo real |

**Nenhum resultado é validado em obra real.** Dados e geometrias são fictícios. A execução de API oficial não será rotulada como observação da interface gráfica. Modelo Blender ilustrativo não será chamado de projeto executivo ou modelo autorável Bonsai. Nenhuma instalação Windows adicional foi autorizada nesta rodada.

Pacote local: `output/releases/demo-ferrovia-vNext/`. Nativos QGIS recomendados em `01-gis-qgis/nativo-02/`; Blender mais recente em `04-visual-blender/nativo-malha-root/`. Arquivos operacionais e evidências permanecem fora do Git.
