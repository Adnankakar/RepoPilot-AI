# RepoPilot AI: Development Notes

## Today's Errors and Solutions

### 1. Root URL returned 404

**Error:** `GET / 404 Not Found`

**Why:** FastAPI mein `/` route define nahi tha.

**Solution:** Root endpoint add karo, ya directly `/docs` and `/health` open karo.

**Lesson:** Browser mein open karne wale routes pehle define karo.

### 2. Favicon returned 404

**Error:** `GET /favicon.ico 404 Not Found`

**Why:** App mein favicon file ya route nahi tha.

**Solution:** Abhi ignore kar sakte hain. Baad mein favicon add karna.

**Lesson:** Har 404 ka matlab app crash hona nahi hai.

### 3. Alembic database URL error

**Error:** `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver`

**Why:** Alembic default placeholder database URL use kar raha tha.

**Solution:** `migrations/env.py` mein SQLAlchemy engine ko project settings se `settings.database_url` dena.

**Lesson:** Database configuration ek hi jagah rakho aur sab jagah reuse karo.

### 4. Missing `pydantic-settings`

**Error:** `ModuleNotFoundError: No module named 'pydantic_settings'`

**Why:** Package Anaconda `base` environment mein tha, `.venv` mein nahi.

**Solution:**

```powershell
python -m pip install pydantic-settings
```

Project ki baaki dependencies bhi `.venv` mein install karo.

**Lesson:** Har Python environment ke packages alag hote hain.

### 5. Anaconda and `.venv` confusion

**Problem:** Terminal mein `(.venv) (base)` dono dikh rahe the.

**Why:** Dono environments active the, jis se Python aur packages ko lekar confusion ho sakta hai.

**Solution:** Correct environment activate karo, phir verify karo:

```powershell
python -c "import sys; print(sys.executable)"
```

Expected path:

```text
D:\RepoPilot AI\.venv\Scripts\python.exe
```

**Lesson:** Project ke liye ek dedicated virtual environment use karo.

---

## Before Running Commands

- [ ] Correct project folder mein ho.
- [ ] `.venv` active hai.
- [ ] Required packages `.venv` mein installed hain.
- [ ] `.env` mein correct database URL hai.
- [ ] PostgreSQL service running hai.
- [ ] Commands run karne ke baad error output carefully read kiya hai.

## Today's Main Takeaway

**Error ko sirf fix mat karo. Uska reason bhi samjho.**

Development mein pehle environment aur configuration verify karo, phir code debug karo.

# RepoPilot AI: Development Learning Notes

## Day 1: Errors and Solutions

### 1. FastAPI root URL returned 404

**Error:** `GET / 404 Not Found`

**Reason:** `/` endpoint define nahi tha.

**Solution:** Root route add karo, ya `/docs` and `/health` open karo.

**Learning:** FastAPI sirf defined routes handle karta hai.

### 2. Favicon returned 404

**Error:** `GET /favicon.ico 404 Not Found`

**Reason:** Favicon file ya route missing thi.

**Solution:** Abhi ignore kar sakte hain.

**Learning:** Har 404 ka matlab app crash hona nahi hai.

### 3. Alembic database URL error

**Error:** `NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver`

**Reason:** Alembic default placeholder database URL use kar raha tha.

**Solution:** `migrations/env.py` mein project settings ka `settings.database_url` use kiya.

**Learning:** Database configuration ko ek central location se manage karo.

### 4. Missing `pydantic-settings`

**Error:** `ModuleNotFoundError: No module named 'pydantic_settings'`

**Reason:** Package Anaconda environment mein tha, `.venv` mein nahi.

**Solution:**

```powershell
python -m pip install pydantic-settings
```

**Learning:** Har Python environment ke packages alag hote hain.

### 5. Anaconda and `.venv` confusion

**Problem:** Terminal mein `(.venv) (base)` dono dikh rahe the.

**Reason:** Anaconda base aur project virtual environment dono active the.

**Solution:** Python path verify kiya:

```powershell
python -c "import sys; print(sys.executable)"
```

Expected path:

```text
D:\RepoPilot AI\.venv\Scripts\python.exe
```

**Learning:** Sirf prompt nahi, Python executable path bhi check karo.

### 6. Dependency verification

**Commands:**

```powershell
python -m pip check
```

```powershell
python -c "import fastapi, sqlalchemy, alembic, pydantic_settings, psycopg; print('All imports successful')"
```

**Result:** `No broken requirements found.` and `All imports successful`.

**Learning:** Development start karne se pehle dependencies verify karo.

### 7. Alembic migration file created

**Command:**

```powershell
python -m alembic revision --autogenerate -m "initial setup"
```

**Result:** Migration file successfully generated.

**Learning:** Migration generate karna aur database par apply karna alag steps hain.

**Next command:**

```powershell
python -m alembic upgrade head
```

Is command ko run karke migration apply karni hai. Database migration abhi successful hui hai, ye confirm nahi hua hai.

---

## Development Checklist

- [ ] Correct project folder open hai.
- [ ] `.venv` Python path verified hai.
- [ ] Required dependencies installed hain.
- [ ] `pip check` successful hai.
- [ ] `.env` mein correct database URL hai.
- [ ] PostgreSQL connection working hai.
- [ ] Alembic migration database par apply ho gayi hai.
- [ ] `/health` endpoint tested hai.

## Today's Main Learnings

1. Error message ko carefully read karo.
2. Python environment aur package installation verify karo.
3. Database URL ko central configuration se manage karo.
4. Migration generate karne ke baad use apply bhi karo.
5. Har fix ko verify karo, sirf command success dekhkar assume mat karo.

python -m pip freeze > requirements.txt