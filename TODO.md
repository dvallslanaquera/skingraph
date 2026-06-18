ASK TO CLAUDE
Whether becoming a 派遣契約 is a good idea compared to 業務委託 and what are the pros and cons

TODO
FEAT: I wanna be able to track products that were never seen before, products that had a low confidence and also I wanna know when the model is not confident about the output.

FEAT: any preprocessing for the VLM? (black-white,
REFACTOR(UI): Wanna make it asyncrhonous. So while the worker is extracting the ingredients, the user can change tabs and the worker won't stop the analysis because of that.

QUERY: should i keep a database of the products so the model is actually matching ingredients with the database instead of reading everytime from scratch? is that legal? can i use it as a caching technique to save money of the VLM? If doable, how can I keep the database updated?

IDEA: run first an lightweight OCR model. Try to match a product. If nothing is match, return a temporary reply and run VLM.

REFACTOR: what if in the image there are more than 1 products?
REFACTOR: what if the image is the front of the product? > search in the web?
DOC: improve README; presentation of the tool is meh

REFACTOR: redo the README file
BUG: there are two warnings about pregnancy

STUDY: how to improve speed of a chatbot
STUDY: what to do from the UX point of view when the model takes too many seconds to return an output?

REFACTOR: what happens if more than 1 product in the image? what happens if the quality is too low?

FEAT: the coach learns what the user likes and dislikes (ex: dislikes sticky products before going to bed, dislikes shiny products in the morning, dislikes specific consistencies or fragances)
FEAT: how to persist a conversation?
FEAT: thumbs up/down and other feedback from the user
FEAT: the Coach is able to remember user preferences/dislikes by talking with them.
FEAT: add a Coach tab for general questions

REFACTOR: hybrid OCR+VLM solution The "OCR-Augmented VLM" Hybrid Architecture
For a skincare ingredient extractor, the most efficient hybrid design is an Asymmetric Multi-Modal Pipeline. Instead of asking a VLM to read a raw image blindly, you use a cheap OCR engine to create a text "draft" and use the VLM strictly for verification, correction, and schema formatting.

Phase 1: Heavy Lifting via Traditional OCR
You pass the raw image of the skincare bottle to a fast, localized, or low-cost OCR engine (e.g., Google Cloud Vision OCR or Apple Vision Framework).

The OCR engine returns a chaotic string of raw text tokens, coordinates, and confidence levels.

Example Raw Output: "INGRED ENTS: Aqua, Glycer_n, N acinam de, Phenoxyethan0l, 1,3-Buty|ene Glycol..." (Notice the glare artifacts and typos).

Phase 2: Structural Gating & Filtering
You use a lightweight deterministic script (regex or basic string matching) to locate the ingredient block anchor words like "Ingredients:" or "成分:".

You strip away irrelevant text on the bottle (like marketing copy, distribution addresses, or recycling symbols) based on OCR bounding boxes.

This dramatically shrinks the visual context space before you hit the expensive model.

Phase 3: The VLM Correction & Structuring Step
Instead of sending a massive image blindly, you pass three inputs to a low-cost VLM (like Gemini 2.0 Flash-Lite or Gemini 2.5 Flash-Lite):

The cropped image region containing the ingredients.

The messy, corrupted text string extracted by the OCR.

A strict JSON schema (Pydantic representation).

The VLM acts as an error-correcting parser rather than a basic transcriber.

---

NOTES
the coach must be able to provide advice about what's the best AM and PM routine, considering the skin type of the client, the genre, their goals (less wrinkless, less dullness, etc.), age, whether they're pregnant or not, any existing skin conditions (eczema, rosacea, etc.), sun damage history, and time and budget to allocate for skincare

- Run UI w/o push
  terminal 1 (backend): poetry run uvicorn src.api.main:app --reload
  terminal 2; npm --prefix ui run dev
