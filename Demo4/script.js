const display = document.querySelector('.display');
const expressionDiv = document.querySelector('.expression');
const resultDiv = document.querySelector('.result');
const buttons = document.querySelector('.buttons-container');

let expression = '';
let result = '';
let memory = 0;

buttons.addEventListener('click', (e) => {
    const value = e.target.innerText;

    if (e.target.tagName !== 'BUTTON') {
        return;
    }

    handleInput(value);
});

document.addEventListener('keydown', (e) => {
    const key = e.key;
    const allowedKeys = '0123456789./*-+%=()';
    const operatorKeys = {
        '/': '/',
        '*': '*',
        '-': '-',
        '+': '+',
        'Enter': '=',
        '=': '=',
    };

    if (allowedKeys.includes(key)) {
        handleInput(key);
    } else if (operatorKeys[key]) {
        handleInput(operatorKeys[key]);
    } else if (key === 'Backspace') {
        handleInput('CE');
    } else if (key === 'Escape') {
        handleInput('C');
    }
});

function handleInput(value) {
    if (value === 'C') {
        expression = '';
        result = '';
    } else if (value === 'CE') {
        expression = expression.slice(0, -1);
    } else if (value === '=') {
        try {
            result = safeEval(expression);
            expression = result.toString();
        } catch (error) {
            result = 'Syntax Error';
        }
    } else if (value === 'sin') {
        expression = `Math.sin(${expression})`;
    } else if (value === 'cos') {
        expression = `Math.cos(${expression})`;
    } else if (value === 'tan') {
        expression = `Math.tan(${expression})`;
    } else if (value === 'log') {
        expression = `Math.log10(${expression})`;
    } else if (value === 'ln') {
        expression = `Math.log(${expression})`;
    } else if (value === '√') {
        expression = `Math.sqrt(${expression})`;
    } else if (value === 'x^y') {
        expression += '**';
    } else if (value === 'n!') {
        try {
            const num = parseInt(expression);
            if (num < 0) {
                result = 'Error';
            } else {
                result = factorial(num);
                expression = result.toString();
            }
        } catch (error) {
            result = 'Error';
        }
    } else if (value === 'M+') {
        memory += parseFloat(result || expression) || 0;
    } else if (value === 'M-') {
        memory -= parseFloat(result || expression) || 0;
    } else if (value === 'MR') {
        expression += memory.toString();
    } else if (value === 'MC') {
        memory = 0;
    } else {
        expression += value;
    }

    updateDisplay();
}

function updateDisplay() {
    expressionDiv.innerText = expression;
    resultDiv.innerText = result || (expression ? '' : '0');
}

function safeEval(expression) {
    return new Function('return ' + expression)();
}

function factorial(n) {
    if (n === 0 || n === 1) {
        return 1;
    }
    return n * factorial(n - 1);
}
