<!-- /CMD -->

git clone <repo-url>
cd REPO-NAME
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run app.py 

<!-- POWERSHELL -->
git clone <repo-url> 
cd REPO-NAME
python -m venv .venv
.\venv\Scripts\Activate
pip install -r requrements.txt
python -m streamlit run app.py
deactivate