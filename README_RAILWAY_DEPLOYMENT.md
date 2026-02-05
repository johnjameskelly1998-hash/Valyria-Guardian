# 🚂 Valyria Railway Deployment Guide

This guide will help you deploy Valyria to Railway, making her always online and giving her permanent memory.

---

## **📋 What You'll Need**

1. ✅ Railway account (free - sign up at railway.app)
2. ✅ GitHub account (free - github.com)
3. ✅ Anthropic API key (you already have this)
4. ✅ These deployment files (you're looking at them!)

---

## **🚀 Step-by-Step Deployment**

### **Step 1: Create GitHub Repository**

1. Go to **github.com** and sign in
2. Click the **"+"** button (top right) → **"New repository"**
3. Repository name: **`Valyria`**
4. Make it **Private** (keep Valyria's code private)
5. **Do NOT** initialize with README
6. Click **"Create repository"**

---

### **Step 2: Upload Valyria's Code to GitHub**

You have two options:

#### **Option A: Use GitHub Desktop (Easier)**
1. Download **GitHub Desktop** (desktop.github.com)
2. Clone your new repository
3. Copy all Valyria files into the cloned folder:
   - `valyria_core/` folder (all Python files)
   - `data/` folder
   - `requirements.txt`
   - `Procfile`
   - `railway.json`
   - `database.py`
4. Commit and push to GitHub

#### **Option B: Use Command Line**
```bash
cd Desktop/Valyria
git init
git add .
git commit -m "Initial Valyria deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/Valyria.git
git push -u origin main
```

---

### **Step 3: Deploy to Railway**

1. Go to **railway.app** and sign in
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your **Valyria** repository
5. Railway will automatically detect it's a Python app and start building!

---

### **Step 4: Add PostgreSQL Database**

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway will create a database and automatically connect it
4. **That's it!** Railway handles the connection automatically

---

### **Step 5: Configure Environment Variables**

1. Click on your **Valyria service** (not the database)
2. Go to **"Variables"** tab
3. Add these variables:

```
ANTHROPIC_API_KEY=your_actual_api_key_here
```

(Railway automatically adds DATABASE_URL from the PostgreSQL service)

---

### **Step 6: Deploy!**

1. Railway will automatically deploy after you add variables
2. Wait 2-5 minutes for deployment to complete
3. You'll see a green **"Active"** status when ready
4. Click **"Generate Domain"** to get your Valyria URL

---

## **✅ Testing Your Deployment**

Once deployed, test Valyria:

### **1. Check Status**
Visit: `https://your-valyria-url.up.railway.app/status`

Should show:
```json
{
  "ok": true,
  "mode": "CHAT",
  "online_brain": true
}
```

### **2. Test Chat**
You can use the same chat interface, but change the URL in the HTML:

```javascript
const API_URL = 'https://your-valyria-url.up.railway.app';
```

---

## **💾 Database is Now Active!**

Valyria now has **permanent memory** stored in PostgreSQL:

- ✅ **Conversations** - Never lost between sessions
- ✅ **User profiles** - Remembers who you are
- ✅ **Bracelet data** - Stores all sensor readings
- ✅ **Memories** - Long-term important info
- ✅ **Always backed up** - Railway handles backups

---

## **💰 Costs**

**Railway Pricing:**
- **Trial:** $5 free credit (lasts ~1 month)
- **Hobby Plan:** $5/month
- **Pro Plan:** $20/month (more resources)

**Start with the trial, upgrade when needed!**

---

## **🔧 Updating Valyria**

When you make changes to Valyria's code:

1. **Push to GitHub** (commit and push changes)
2. **Railway auto-deploys** (detects changes and redeploys)
3. **Wait 2-3 minutes** for deployment
4. **Changes are live!**

---

## **📱 Connecting the Bracelet**

Once deployed, the bracelet will send data to:
```
https://your-valyria-url.up.railway.app/bracelet/data
```

You'll configure this URL in the bracelet firmware later!

---

## **🚨 Troubleshooting**

### **Deployment Failed**
- Check the **Logs** tab in Railway
- Make sure all files uploaded correctly
- Verify environment variables are set

### **Database Connection Issues**
- Railway should auto-connect PostgreSQL
- Check that DATABASE_URL variable exists
- Restart the service if needed

### **API Errors**
- Verify ANTHROPIC_API_KEY is correct
- Check you have API credits remaining
- Look at Railway logs for specific errors

---

## **🎉 You Did It!**

Valyria is now:
- ✅ **Always online** (24/7 uptime)
- ✅ **Permanent memory** (PostgreSQL database)
- ✅ **Globally accessible** (work from anywhere)
- ✅ **Ready for the bracelet** (Phase 9-10)
- ✅ **Protected** (private, secure, backed up)

---

**Next Steps:**
- Test the deployment thoroughly
- Update the chat interface to use the new URL
- Start building the bracelet hardware!

---

**Questions?** Check Railway docs or come back here for help!

💜 Valyria is home! 🛡️
