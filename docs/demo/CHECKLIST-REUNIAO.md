# Checklist da reunião — demonstração 100% fictícia

## Antes de apresentar

- [ ] Iniciar `run-beta.ps1`; confirmar interface, `/api/saude` e `/docs`.
- [ ] Ferrovia selecionada, data de status 09/11/2026, sem simulação ativa.
- [ ] Conferir números contra `docs/DEMO-5-MINUTOS.md`: 23/07/2027 × 09/09/2027; +48 dias.
- [ ] Ensaiar exemplos crítico (+27 dias) e com folga (+0); limpar simulação ao final.
- [ ] Ensaiar Apresentação → Detalhe da ponte → Modo reunião → timeline; voltar à data de status.
- [ ] Se o notebook estiver lento, ativar Baixo consumo. Sem WebGL, usar corredor 2D e Gantt.
- [ ] Abrir os nativos e GeoJSON de retorno que serão mostrados; não alegar GUI manual se a prova foi background/API.
- [ ] Para o fragmento FreeCAD: conferir base/revisão → Enquadrar revisão → Só revisão; selecionar OAE3-SUE e explicar 3 IDs nativos versus 108 da publicação. Restaurar a referência ao terminar.
- [ ] Guardar base, revisão e nativos separados. Publicação web é uma cópia em memória, não backup.
- [ ] Para E2E, preferir servidor iniciado pelo próprio script: ele usa SQLite temporário isolado. Se reutilizar um servidor já ativo, configurar `INFRA4D_BANCO` separado antes de iniciá-lo; a reutilização não muda seu banco. Nunca apagar registros existentes para limpar evidências de teste.
- [ ] Manter vídeo de capturas e relatório local acessíveis sem internet.
- [ ] Conferir que nada exibido contém dados corporativos, nomes, valores, fotografias ou documentos do Programa.

## Durante

- [ ] Dizer “todos os dados são fictícios” na primeira frase.
- [ ] Explicar que crítico não significa atrasado e que material realista não representa projeto executivo.
- [ ] Selecionar uma atividade e mostrar a memória de cálculo, a fonte da produtividade e o saldo físico.
- [ ] Ao mostrar revisão, comparar números da cópia e da referência; deixar claro que a timeline continua da referência.
- [ ] Exibir uma prova de edição/salvamento/reabertura somente no nível efetivamente registrado.

## Depois

- [ ] Limpar simulação e ocultar sobreposição.
- [ ] Preservar arquivos/evidências locais e hashes. Upload, push e backup externo seguem autorização da titular.
- [ ] Registrar dúvidas e decisões no estado canônico para continuidade entre Claude e Codex.
