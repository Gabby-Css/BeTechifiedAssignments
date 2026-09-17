require('dotenv').config();
const express = require('express');
const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json());

app.get('/', (req, res) => {
  res.send('My Week 2 API!');
});

app.post('/user', (req, res) => {
  const { name, email } = req.body;
  res.send(`Hello, ${name}!`);
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
}); 

