// Import the functions you need from the SDKs you need
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-app.js";
import { getAuth, onAuthStateChanged, signInWithPopup, GoogleAuthProvider, signOut, createUserWithEmailAndPassword, signInWithEmailAndPassword, sendPasswordResetEmail, updateProfile } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore.js";

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

export { app, db, auth, provider, signInWithPopup, signOut, onAuthStateChanged, createUserWithEmailAndPassword, signInWithEmailAndPassword, sendPasswordResetEmail, updateProfile };

// Global Auth State Listener to update Navigation UI
onAuthStateChanged(auth, (user) => {
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
