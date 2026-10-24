# Gemma 4 Agent: Public Config Draws

One row per scored version of the public notebooks attached to the Kaggle competition
Google - The Gemma 4 Developer Agent (gemma-4-developer-agent), read 2026-10-22 05:51 to 06:26 UTC, plus 4 rows of my own
submissions of two of the same public file sets. Each row carries the version's public score and the number of public
tasks that score means. Where the version's code could be traced to the files it writes to submission.zip, it also
carries a hash of those files, so identical configs can be grouped and their repeated draws compared.

Coverage: 274 public notebooks listed; 4 of them have a version history that could not be read
(ayushmldixit1/notebook46419a07d8, bang1850/notebook67dada2eb5, littlecow0426/getting-started-gemma-4-developer-agent, tuynnguynee/notebook057a67b5a8); 66 have at least one scored version;
141 scored public versions. 40 could be traced to the files they submit. 38 have a bundle dictionary
whose write to submission.zip could not be tied to exactly one known, unedited dictionary (no traceable write:
22; a write not tied to one dictionary: 15; different bundles written: 1; a code cell that does not
parse: 0). 63 have no bundle dictionary that can be read without running the code. Only the 40 traced
versions are grouped; 6 file sets appear at least twice.

## Files

- public_config_draws.csv: the table (one row per scored version, UTF-8).
- board_blocks.csv: the public leaderboard of 2026-10-22 06:35 UTC reduced to one row per displayed score (teams, rank range,
  median and mean submission count per team). No team names.
- census_meta.json: when and how the table was read.

## Columns of public_config_draws.csv

- config_label: for file sets seen at least twice, the earliest public version carrying them (title, version, author); blank otherwise.
- files_sha256: sha256 of json.dumps(FILES, sort_keys=True), where FILES is the dictionary of bundle paths to file text
  that the version's own code writes to submission.zip. Equal hashes mean the same file texts were written to
  submission.zip by every write the trace could follow.
- author, author_username: the notebook author's Kaggle display name and username.
- notebook_ref, notebook_title: the notebook (owner/slug) and its title at read time.
- version, version_url, version_date_utc: the notebook version that produced the scored submission, a link to it, and when it was created.
- public_score: the public score shown for that version (Kaggle truncates to 2 decimals).
- tasks_of_58: the number of public tasks that score means. 58 is the only task count from 30 to 78 that reproduces
  every displayed score in this table and on the board. Some larger counts also fit scores this low, but the
  competition's data page puts each half near 60 (about 120 tasks, evenly divided). Checked in the companion notebook.
- source: public_notebook, or own_submission for my own submissions of public file sets. These are all of my
  submissions of those two file sets, each made after that file set's first public run; ids and dates are not published.
- hash_kind: files (traced to the dictionary written to submission.zip), ambiguous (a bundle dictionary exists but
  the write could not be tied to exactly one known, unedited dictionary), code_text (no bundle dictionary readable
  without running the code) or unavailable. Only files rows are grouped.
- hash_method: for files rows, the dictionary and the call or ZipFile block that writes submission.zip; for
  ambiguous rows, why the write could not be traced.
- code_text_sha256: sha256 of the version's code text; tells versions apart even when they cannot be grouped.
- files_in_bundle: the paths inside the submitted dictionary.

## How it was read

- Notebook list: the Kaggle API, `kaggle kernels list --competition gemma-4-developer-agent`, every page.
- Scores: each notebook's public version history, the same pages anyone can open.
- Hashes: each scored version's code was read as text and walked statement by statement with Python's ast module.
  Dictionary literals and copies were traced to the one written to submission.zip, and every zip write had to put
  that dictionary's own texts into the archive unchanged. Nothing was executed. A dictionary edited after it is
  defined, a write that adds anything else, a version that writes different bundles, or a cell that does not parse
  makes the version ambiguous; ambiguous versions are left out of every group.

## Caveats

- A version's score is a single draw; identical files do not score the same from run to run (the companion notebook
  measures the spread).
- Public notebooks are a selected sample: people choose what to publish and which versions to keep.
- Titles are as read; authors may rename notebooks later.

## Not included

No config files, prompts or code from any author, no competition data, and no private submission ids.

## License

The table (the compilation, hashes and derived columns) is CC BY 4.0. Notebook titles and author names are as
published on Kaggle, and every notebook remains its author's work.

## Credits

Every notebook in the table, by its author's display name:

- Agent Trainer (lucifer19/agentic-counterexample-lab)
- Agent Trainer (lucifer19/agentic-verified-checkout-v2)
- Agent Trainer (lucifer19/black-cat-swe-agent-pack-instinct)
- Ahmad Alalony (ahmadalalony/gemma-4-starter-inside-the-harness-e-63dd0e)
- AILEFEIRE MUHATI (alfira17/the-gemma-4-developer-agent-competition)
- AlekseiProvorov (leoprovorov/gemma-4-agent-working-baseline)
- AlekseiProvorov (leoprovorov/gemma-4-the-complete-guide-expanded-full)
- AlekseiProvorov (leoprovorov/single-agent-anytime-patch)
- Arlene (lynnsakurai/gemma-4-budget-fit-agent-w-bounded-rescue)
- Chandan Kumar Barada (ckskaggle/g4ca-basv1-0)
- Dante (ccuuuuy/dante-agent)
- Davis (davis0178/gemma-4-agent-baseline)
- Deian (zhongyanxu/gemma-4-walkthrough-first-submission)
- Den Pugovkin (denpugovkin/gemma-4-same-check-before-and-after)
- Dmitrii Gluzdov (dmitriigluzdov/gemma-4-public-agent-ideas-and-evidence)
- Dmitrii Gluzdov (dmitriigluzdov/gemma-4-task-soundness-serving-and-evaluation)
- Eesh saxena (eeshsaxena/gemma4-baseline-agent)
- Ertuğrul Özer (ozertuu/gemma-4-gold-submit)
- Ertuğrul Özer (ozertuu/gemma-4-v4-submit)
- haideptry (haideptry/gemma-develop-first-try)
- Hanh Tran (honghanhhh/gemma-4-baseline-lb-0-24)
- Hanif Noer Rofiq (hanifnoerrofiq/patchsmith-gemma-4-developer-agent)
- Harish Yadav (harishyadav0506/black-cat-swe-agent)
- Hibachi Fried Rice (samvalladares/gemma-4-agent-budget-fit-single-agent)
- Hitarth Jain (hitarthjain0/gemma-4-apex-budget-fit-single-agent)
- hsiaosuan (hsiaosuan/gemma-developer-agent-0-13-submission)
- icfoer (icfoer/gemma4-developer-agent-lora-200-test)
- Igor Zharov (flexonafft/gemma-4-budget-aware-coding-agent-v2)
- Jeki Wan Taufik (jek1wantaufik/gemma-4-developer-agent-lean)
- Jingshui Fu (jingshuifu/gemma-4-dev-agent-budget-fit-v1)
- Jingshui Fu (jingshuifu/gemma-4-dev-agent-lb024)
- Juna1013 (juna1013/gemma4-agent-submission)
- K.THARUN KUMAR (tharunkumar369/gemma-4-developer-agent-top-1-master-baseline)
- Kaito Fukami (kaitofukami/gemma4-agent-v8-shell)
- KAIWALYA RAUT (kaiwalyaatulraut/google-the-gemma-4)
- KevlarZanderChi (kevlarzanderchi/gemma4-prompt-improvement-agent)
- Kizabgd123 (kiza123123/judgeguard-gemma-4-autonomous-developer-agent)
- KOUSHIK KUMAR DINDA (koushikkumardinda/gemma-4-developer-agent-end-to-end-adk-starter)
- Kozykorpesh (kozykappa/gemma-4-triad-lb-score-0-03)
- Lavin Wins (lavinwins/gemma-4-autonomous-developer-agent-calibrated-sin)
- Liujiahua (liujiahua2358/gemma-4-v0-walkthrough-first-submission)
- lyambdadelta (lambdaderta/single-agent-tuning)
- Maram Ali (msama01/gemma-4-developer-agent-eda)
- Matterhorn3838 (matterhorn3838/gemma-4-superagent)
- Matterhorn3838 (matterhorn3838/gemma-gemini-the-ultimate-duo)
- Mizero Lucky Gall (mizeroluckygall/gemma-4-agent-eda-agent-validator)
- Mizero Lucky Gall (mizeroluckygall/pathfinder-gemma-4-agent-eda-baseline)
- Nilanjan_Saha123 (nilanjansaha123/gemma-4-agent-eda-adk-starter)
- Nilanjan_Saha123 (nilanjansaha123/gemma-4-dev-agent-contract-first-1-agent-bundle)
- Nilanjan_Saha123 (nilanjansaha123/gemma-4-v5)
- Oleksii Zhukov (zhukovoleksiy/gemma-4-walkthrough-findings-submission)
- parthenos (nihilisticneuralnet/0-10-gemma-4-developer-agent-submission)
- parthenos (nihilisticneuralnet/gemma-4-developer-agent-direct-code-verifier)
- prvsiyan (prvsiyan/gemma-and-the-shape-of-doubt)
- rainy-cloudss (rainycloudss/gemma-4-agent-apex-v16-tdd-reproducer)
- Rishav Yadav (rishavae/gemma4)
- Roman Rozen (romanrozen/gemma-eda-baseline-for-a-start-lb-top-1)
- Soham Milind Petkar (starksource/getting-started-gemma-4-developer-agent)
- sont (jvnhonglei/gemma-4-superagent-reproduction)
- Sushanth Tiruvaipati (sushanthtiruvaipati/gemma4-swe-agent-v11-matterhorn)
- Taylor Clark (taylorclark637/gemmagraph-swe-offline-code-graph-developer-agent)
- tomasz szyrowski (tomaszszyrowski/gemma4-day1-baseline)
- TwangyGarlic449 (twangygarlic449/gemma-super-basic)
- Wilmer E. Henao (verracodeguacas/gemma-4-agent-budget-fit-single-agent)
- yiyu0716 (yiyu0716/g4-pack-yiyu-v19-fixed-trace-t7p5)
- Дворкин Евгений Владимирович (evgendvorkin/google-the-gemma-4)
