const express = require("express");
const app = express();
app.use(express.json()); // lets the server read JSON from the request body

app.post("/user", (req, res) => {
  const { name, email } = req.body;
  console.log("Got new user:", name, email);
  res.status(201).json({ message: "User created!", name, email });
});
// Error handling
app.post('/user', (req, res) => {
  const { name, email } = req.body;

  if (!name || !email) {
    return res.status(400).json({ error: 'Both name and email are required.' });
  }

  res.send(`Hello, ${name}!`);
});

app.get('/user/:id', (req, res) => {
  const { id } = req.params;
  res.send(`User ${id} profile`);
});

app.listen(3000, () => console.log("Server running on port 3000"));