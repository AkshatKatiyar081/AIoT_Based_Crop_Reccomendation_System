# Import libraries
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from joblib import dump

df = pd.read_csv("Crop_recommendation.csv")
print(df.head())

# Separate features and target
X = df.drop("label", axis=1)   # features
y = df["label"]                # target

# Train-test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# Initialize scaler
scaler = StandardScaler()

# Fit ONLY on training data, then transform both
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

# Save scaler for later use (important for Streamlit/app)
dump(scaler, "scaler.joblib")

# Optional: check result
print("\nScaled Training Data Sample:")
print(X_train_scaled[:5])

print("\nScaler saved as 'scaler.joblib'")

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import numpy as np

# Initialize model
model = RandomForestClassifier(n_estimators=100, random_state=42)

# Train model on scaled data
model.fit(X_train_scaled, y_train)

# Predictions on test data
y_pred = model.predict(X_test_scaled)

# Accuracy
accuracy = accuracy_score(y_test, y_pred)
print(f"Accuracy: {accuracy * 100:.2f}%")

# Detailed report
print("\nClassification Report:")
print(classification_report(y_test, y_pred))

# Save model
dump(model, "crop_model.joblib")
print("\nModel saved as 'crop_model.joblib'")