// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, onAuthStateChanged, signInWithPopup, GoogleAuthProvider, signOut, createUserWithEmailAndPassword, signInWithEmailAndPassword, sendPasswordResetEmail, updateProfile, signInWithCustomToken } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";
import { getFirestore, doc, getDoc, setDoc, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";

// NotiCatcher Firebase Configuration
const firebaseConfig = {
  apiKey: "AIzaSyDZQvThvFF6hRcMpYkduerNVdxU6FGxpAs",
  authDomain: "noticatcher-eb157.firebaseapp.com",
  projectId: "noticatcher-eb157",
  storageBucket: "noticatcher-eb157.firebasestorage.app",
  messagingSenderId: "1077494708034",
  appId: "1:1077494708034:web:dba3823287ee863543fadb",
  measurementId: "G-YDFC9DQCMM"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
const db = getFirestore(app);

export { app, db, auth, provider, signInWithPopup, signOut, onAuthStateChanged, createUserWithEmailAndPassword, signInWithEmailAndPassword, sendPasswordResetEmail, updateProfile, signInWithCustomToken };

const ensuredUserDocPromises = new Map();

async function ensureUserDoc(user) {
    if (!user || !user.uid) return;
    if (ensuredUserDocPromises.has(user.uid)) return ensuredUserDocPromises.get(user.uid);

    const p = (async () => {
        const userRef = doc(db, "users", user.uid);
        const snap = await getDoc(userRef);
        const now = serverTimestamp();
        const providerIds = Array.isArray(user.providerData)
            ? user.providerData.map((p) => p && p.providerId).filter(Boolean)
            : [];

        if (!snap.exists()) {
            await setDoc(
                userRef,
                {
                    uid: user.uid,
                    email: user.email || null,
                    displayName: user.displayName || null,
                    photoURL: user.photoURL || null,
                    providerIds,
                    grade: "free",
                    createdAt: now,
                    updatedAt: now,
                },
                { merge: true }
            );
            return;
        }

        const data = snap.data() || {};
        const updates = {
            uid: user.uid,
            email: user.email || null,
            displayName: user.displayName || null,
            photoURL: user.photoURL || null,
            providerIds,
            updatedAt: now,
        };
        if (!Object.prototype.hasOwnProperty.call(data, "grade")) {
            updates.grade = "free";
        }

        await setDoc(userRef, updates, { merge: true });
    })().catch((err) => {
        ensuredUserDocPromises.delete(user.uid);
        throw err;
    });

    ensuredUserDocPromises.set(user.uid, p);
    return p;
}

// Global Auth State Listener to update Navigation UI
onAuthStateChanged(auth, (user) => {
    if (user) {
        ensureUserDoc(user).catch((e) => {
            console.warn("Failed to ensure users/{uid} doc", e);
        });
    }
    const authLink = document.getElementById('auth-link');
    if (authLink) {
        if (user) {
            authLink.innerHTML = `<i class='bx bx-user-circle'></i> Dashboard`;
            authLink.classList.remove('btn-glass');
            authLink.classList.add('btn-primary');
        } else {
            authLink.innerHTML = `Login / My Info`;
            authLink.classList.remove('btn-primary');
            authLink.classList.add('btn-glass');
        }
    }
});
